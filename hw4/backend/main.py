"""Account, catalogue, inventory, and image API for the Campus Customs storefront."""

import json
import base64
import hashlib
import hmac
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from .audit import begin_agent_audit, finish_agent_audit
    from .agent import get_agent
    from .models import (
        AgentCustomer,
        ChatHistoryMessage,
        ChatHistoryResponse,
        ChatReply,
        ChatRequest,
        ChatTurn,
        ProductCard,
        ProductMatch,
    )
    from .tools import ShopData
except ImportError:  # Support `uvicorn main:app` from the backend/ directory.
    from audit import begin_agent_audit, finish_agent_audit
    from agent import get_agent
    from models import AgentCustomer, ChatHistoryMessage, ChatHistoryResponse, ChatReply, ChatRequest, ChatTurn, ProductCard, ProductMatch
    from tools import ShopData


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "campus_customs.db"
PRODUCT_IMAGES = PROJECT_ROOT / "data" / "products"
PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
# The supplied seed database uses this legacy PBKDF2-SHA256 format, which does
# not store its iteration count. New account hashes use self-describing scrypt.
LEGACY_PBKDF2_ITERATIONS = 120_000
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
SESSION_SECRET = os.environ.get("CAMPUS_CUSTOMS_SESSION_SECRET")
SESSION_KEY = SESSION_SECRET.encode("utf-8") if SESSION_SECRET else secrets.token_bytes(32)
COOKIE_SECURE = os.environ.get("APP_ENV", "development").lower() == "production"
LABELED_SECRET_RE = re.compile(
    r"(?i)\b(password|passphrase|passcode|pin|security code|verification code|api key|access token|secret)\b"
    r"\s*(?:is|:|=)\s*([^\s,;]+)"
)
PAYMENT_NUMBER_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
MAX_AGENT_CONTEXT_CHARACTERS = 6000

app = FastAPI(
    title="Campus Customs API",
    description="Account, catalogue, inventory, and product image services for the Campus Customs storefront.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def connect_database() -> sqlite3.Connection:
    """Open the supplied database in read-only mode."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail="The Campus Customs catalogue database is unavailable.")
    connection = sqlite3.connect(f"{DATABASE_PATH.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def connect_accounts_database() -> sqlite3.Connection:
    """Open the account database for the authentication endpoints."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(status_code=503, detail="The Campus Customs account database is unavailable.")
    connection = sqlite3.connect(DATABASE_PATH.as_posix(), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


class AccountCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=1024)
    password_confirmation: str = Field(min_length=1, max_length=1024)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter both a first and last name.")
        return value

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @model_validator(mode="after")
    def passwords_must_match(self) -> "AccountCreate":
        if self.password != self.password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self


class AccountLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Hash a new password with Argon2id and a fresh random salt."""
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify current Argon2id hashes and the seed database's PBKDF2 hashes."""
    try:
        parts = encoded_hash.split("$")
        if encoded_hash.startswith("$argon2id$"):
            try:
                return PASSWORD_HASHER.verify(encoded_hash, password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return False
        if len(parts) == 3 and parts[0] == "pbkdf2_sha256":
            _, salt, expected_hex = parts
            expected = bytes.fromhex(expected_hex)
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt.encode("utf-8"), LEGACY_PBKDF2_ITERATIONS
            )
            return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError, OverflowError):
        return False
    return False


def make_session_token(user_id: int) -> str:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = _b64encode(f"{user_id}:{expires_at}".encode("ascii"))
    signature = hmac.new(SESSION_KEY, payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def session_user_id(token: Optional[str]) -> Optional[int]:
    if not token:
        return None
    try:
        payload, signature_text = token.split(".", 1)
        expected = hmac.new(SESSION_KEY, payload.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_text)):
            return None
        user_text, expires_text = _b64decode(payload).decode("ascii").split(":", 1)
        if int(expires_text) <= int(time.time()):
            return None
        return int(user_text)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        "campus_customs_session",
        make_session_token(user_id),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "first_name": row["first_name"] or row["name"].split(" ", 1)[0],
        "last_name": row["last_name"] or "",
        "email": row["email"],
    }


def ensure_chat_history_table() -> None:
    """Create the per-user chat log table and lookup index when first needed."""
    with closing(connect_accounts_database()) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS chat_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "role TEXT NOT NULL CHECK (role IN ('user', 'assistant')), "
            "content TEXT NOT NULL, "
            "product_ids TEXT NOT NULL DEFAULT '[]', "
            "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
            ")"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_history_user_id_id ON chat_history(user_id, id)"
        )
        connection.commit()


def authenticated_chat_customer(request: Request) -> sqlite3.Row | None:
    """Resolve the chat customer exclusively from the signed HTTP-only session cookie."""
    user_id = session_user_id(request.cookies.get("campus_customs_session"))
    if user_id is None:
        return None
    with closing(connect_accounts_database()) as connection:
        return connection.execute(
            "SELECT id, name, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def save_chat_exchange(user_id: int, user_message: str, assistant_reply: str, product_ids: list[str]) -> None:
    """Persist one user/assistant exchange scoped to the authenticated database user ID."""
    safe_user_message = redact_sensitive_chat_text(user_message)
    safe_assistant_reply = redact_sensitive_chat_text(assistant_reply)
    with closing(connect_accounts_database()) as connection:
        connection.executemany(
            "INSERT INTO chat_history (user_id, role, content, product_ids) VALUES (?, ?, ?, ?)",
            [
                (user_id, "user", safe_user_message, "[]"),
                (user_id, "assistant", safe_assistant_reply, json.dumps(product_ids)),
            ],
        )
        connection.commit()


def redact_sensitive_chat_text(text: str) -> str:
    """Redact common labeled secrets and payment card numbers before saving conversation text."""
    text = LABELED_SECRET_RE.sub(lambda match: f"{match.group(1)}: [redacted]", text)
    return PAYMENT_NUMBER_RE.sub("[redacted payment number]", text)


def build_agent_transcript(history: list[ChatTurn], latest_message: str) -> str:
    """Keep the newest conversation context within a fixed input size for cost and latency."""
    latest_line = f"Customer's latest message: {redact_sensitive_chat_text(latest_message)}"
    remaining = MAX_AGENT_CONTEXT_CHARACTERS - len(latest_line)
    recent_lines: list[str] = []
    for turn in reversed(history):
        label = "Customer" if turn.role == "user" else "Assistant"
        content = redact_sensitive_chat_text(turn.content)
        prefix = f"{label}: "
        available = remaining - len(prefix) - 1
        if available <= 0:
            break
        if len(content) > available:
            content = "…" + content[-(available - 1):] if available > 1 else content[-available:]
        line = prefix + content
        recent_lines.append(line)
        remaining -= len(line) + 1
        if remaining <= 0:
            break
    return "\n".join([*reversed(recent_lines), latest_line])


def parse_json_list(value: str) -> list[str]:
    try:
        parsed: Any = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value] if value else []
    return parsed if isinstance(parsed, list) else []


def product_payload(
    row: sqlite3.Row, sizes: Optional[list[sqlite3.Row]] = None
) -> dict[str, Any]:
    image_name = Path(row["image_file_path"]).name
    payload: dict[str, Any] = {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "description": row["description"],
        "colors": parse_json_list(row["colors"]),
        "search_tags": parse_json_list(row["search_tags"]),
        "image_url": f"/api/images/{quote(image_name)}",
        "price": row["price"],
    }
    if sizes is not None:
        payload["sizes"] = [{"size": size["size"], "quantity": size["quantity"]} for size in sizes]
    return payload


def short_description(description: str, max_characters: int = 150) -> str:
    """Trim a catalogue description for a compact chat result card."""
    clean_description = " ".join(description.split())
    if len(clean_description) <= max_characters:
        return clean_description
    shortened = clean_description[: max_characters + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened}…"


def load_product_matches(product_ids: list[str]) -> list[ProductMatch]:
    """Resolve saved or agent-selected catalogue IDs into current, verified cards."""
    product_ids = list(dict.fromkeys(product_ids))[:8]
    if not product_ids:
        return []
    placeholders = ", ".join("?" for _ in product_ids)
    with closing(connect_database()) as connection:
        rows = connection.execute(
            f"SELECT * FROM catalogue WHERE product_id IN ({placeholders})", product_ids
        ).fetchall()
        row_by_id = {row["product_id"]: row for row in rows}
        cards = []
        for product_id in product_ids:
            row = row_by_id.get(product_id)
            if row is None:
                continue
            sizes = connection.execute(
                "SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY id",
                (product_id,),
            ).fetchall()
            product = ProductCard.model_validate(product_payload(row, sizes))
            cards.append(
                ProductMatch(
                    product_id=product.product_id,
                    name=product.name,
                    garment_type=product.garment_type,
                    image_url=product.image_url,
                    price=product.price,
                    short_description=short_description(product.description),
                    sizes=product.sizes,
                )
            )
    return cards


def load_chat_history(user_id: int) -> list[ChatHistoryMessage]:
    """Read one user's messages only and hydrate any historical product cards from current data."""
    ensure_chat_history_table()
    with closing(connect_accounts_database()) as connection:
        rows = connection.execute(
            "SELECT id, role, content, product_ids, created_at FROM chat_history "
            "WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
    parsed_product_ids: list[list[str]] = []
    for row in rows:
        try:
            product_ids = json.loads(row["product_ids"] or "[]")
        except (json.JSONDecodeError, TypeError):
            product_ids = []
        parsed_product_ids.append(product_ids if isinstance(product_ids, list) else [])
    all_product_ids = list(dict.fromkeys(
        product_id for product_ids in parsed_product_ids for product_id in product_ids
        if isinstance(product_id, str)
    ))
    matches = {item.product_id: item for item in load_product_matches(all_product_ids)}
    return [
        ChatHistoryMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            products=[matches[product_id] for product_id in product_ids if product_id in matches],
        )
        for row, product_ids in zip(rows, parsed_product_ids)
    ]


def load_recent_chat_turns(user_id: int, limit: int = 12) -> list[ChatTurn]:
    """Load recent conversation text for the agent, scoped to one authenticated user."""
    ensure_chat_history_table()
    with closing(connect_accounts_database()) as connection:
        rows = connection.execute(
            "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [ChatTurn(role=row["role"], content=row["content"]) for row in reversed(rows)]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/chat/history", response_model=ChatHistoryResponse)
def chat_history(request: Request) -> ChatHistoryResponse:
    """Return chat history for the signed-in customer, or an empty guest history."""
    customer = authenticated_chat_customer(request)
    if customer is None:
        return ChatHistoryResponse(authenticated=False)
    return ChatHistoryResponse(
        authenticated=True,
        messages=load_chat_history(int(customer["id"])),
    )


@app.post("/api/chat", response_model=ChatReply)
async def chat(chat_request: ChatRequest, request: Request) -> ChatReply:
    """Answer a storefront chat message using current catalogue and stock data."""
    message = chat_request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a message to chat with the shop assistant.")

    customer = authenticated_chat_customer(request)
    if customer is not None:
        ensure_chat_history_table()
        # Authenticated context comes from the backend's user-scoped database history.
        history = load_recent_chat_turns(int(customer["id"]))
        customer_context = AgentCustomer(name=customer["name"], email=customer["email"])
    else:
        # Guests may keep a short conversation in the browser, but it is never persisted.
        history = chat_request.history[-12:]
        customer_context = None

    transcript = build_agent_transcript(history, message)
    audit_token = begin_agent_audit()
    try:
        result = await get_agent().run(
            transcript,
            deps=ShopData(
                database_path=DATABASE_PATH,
                customer=customer_context,
                page_context=chat_request.page_context,
            ),
            model_settings={"max_tokens": 700},
        )
    except RuntimeError as error:
        finish_agent_audit(
            audit_token,
            stop_reason=f"run_failed:{type(error).__name__}",
            result_summary={"status": "failed", "error_type": type(error).__name__},
        )
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        finish_agent_audit(
            audit_token,
            stop_reason=f"run_failed:{type(error).__name__}",
            result_summary={"status": "failed", "error_type": type(error).__name__},
        )
        # Do not send provider exceptions, request headers, or environment data to the browser.
        raise HTTPException(
            status_code=502,
            detail="The shop assistant could not answer right now. Please try again.",
        ) from error

    try:
        answer = result.output
        cards = load_product_matches(answer.product_ids)
        if customer is not None:
            save_chat_exchange(
                int(customer["id"]),
                message,
                answer.reply,
                [card.product_id for card in cards],
            )
    except Exception as error:
        finish_agent_audit(
            audit_token,
            stop_reason=f"postprocessing_failed:{type(error).__name__}",
            result_summary={"status": "failed", "error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=502,
            detail="The shop assistant could not complete that answer right now. Please try again.",
        ) from error
    finish_agent_audit(
        audit_token,
        stop_reason="structured_final_answer_returned",
        result_summary={"status": "completed", "product_card_count": len(cards)},
    )
    return ChatReply(reply=answer.reply, products=cards)


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_account(account: AccountCreate, response: Response) -> dict[str, Any]:
    email = account.email
    full_name = f"{account.first_name} {account.last_name}"
    encoded_hash = hash_password(account.password)
    try:
        with closing(connect_accounts_database()) as connection:
            existing = connection.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)
            ).fetchone()
            if existing is not None:
                raise HTTPException(status_code=409, detail="An account with this email already exists.")
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, first_name, last_name) "
                "VALUES (?, ?, ?, ?, ?)",
                (full_name, email, encoded_hash, account.first_name, account.last_name),
            )
            connection.commit()
            user_id = cursor.lastrowid
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from error
    set_session_cookie(response, int(row["id"]))
    return public_user(row)


@app.post("/api/auth/login")
def login_account(account: AccountLogin, response: Response) -> dict[str, Any]:
    with closing(connect_accounts_database()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (account.email,)
        ).fetchone()
        if row is None or not verify_password(account.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        if row["password_hash"].startswith("pbkdf2_sha256$"):
            upgraded_hash = hash_password(account.password)
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?", (upgraded_hash, row["id"])
            )
            connection.commit()
            row = connection.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    set_session_cookie(response, int(row["id"]))
    return public_user(row)


@app.get("/api/auth/me")
def current_account(request: Request) -> dict[str, Any]:
    user_id = session_user_id(request.cookies.get("campus_customs_session"))
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sign in to view this account.")
    with closing(connect_accounts_database()) as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Sign in to view this account.")
    return public_user(row)


@app.post("/api/auth/logout")
def logout_account(response: Response) -> dict[str, str]:
    response.delete_cookie(
        "campus_customs_session", path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax"
    )
    return {"status": "signed out"}


@app.get("/api/products")
def list_products() -> list[dict[str, Any]]:
    with closing(connect_database()) as connection:
        rows = connection.execute("SELECT * FROM catalogue ORDER BY rowid").fetchall()
    return [product_payload(row) for row in rows]


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    with closing(connect_database()) as connection:
        row = connection.execute(
            "SELECT * FROM catalogue WHERE product_id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        sizes = connection.execute(
            "SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY id",
            (product_id,),
        ).fetchall()
    return product_payload(row, sizes)


@app.get("/api/images/{image_name}")
def get_product_image(image_name: str) -> FileResponse:
    if Path(image_name).name != image_name:
        raise HTTPException(status_code=404, detail="Image not found.")
    image_path = (PRODUCT_IMAGES / image_name).resolve()
    if image_path.parent != PRODUCT_IMAGES.resolve() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type)
