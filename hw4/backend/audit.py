"""Append-only, privacy-conscious records for Campus Customs agent runs."""

from __future__ import annotations

import fcntl
import inspect
import json
import math
import os
import sqlite3
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

try:
    from .models import InventoryLookupResult, ProductLookupResult
except ImportError:  # Support `uvicorn main:app` from the backend/ directory.
    from models import InventoryLookupResult, ProductLookupResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = PROJECT_ROOT / "output" / "audit_trail.json"
_CURRENT_RUN: ContextVar[list[dict[str, Any]] | None] = ContextVar("campus_customs_audit_run", default=None)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _short(value: str, limit: int = 90) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _known_size(ctx: Any, value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    database_path = getattr(getattr(ctx, "deps", None), "database_path", None)
    if not isinstance(database_path, Path) or not database_path.is_file():
        return None
    try:
        connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT DISTINCT size FROM inventory").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    requested = value.strip().casefold()
    return next((row[0] for row in rows if isinstance(row[0], str) and row[0].casefold() == requested), None)


def _safe_arguments(name: str, bound: inspect.BoundArguments, result: Any, ctx: Any) -> dict[str, Any]:
    """Keep only bounded filters or canonical database identifiers; never store user queries."""
    values = bound.arguments
    if name == "search_catalogue":
        max_price = values.get("max_price")
        if isinstance(max_price, (int, float)) and math.isfinite(max_price) and 0 <= max_price <= 10_000:
            safe_max_price: float | None = round(float(max_price), 2)
        else:
            safe_max_price = None
        limit = values.get("limit")
        safe_limit = max(1, min(int(limit), 12)) if isinstance(limit, int) else 6
        sort_by = values.get("sort_by")
        if sort_by not in {"relevance", "price_low_to_high", "price_high_to_low"}:
            sort_by = "relevance"
        return {
            "query": "[omitted for privacy]",
            "max_price": safe_max_price,
            "garment_type": "[omitted for privacy]" if values.get("garment_type") else None,
            "size": _known_size(ctx, values.get("size")),
            "in_stock_only": bool(values.get("in_stock_only", False)),
            "sort_by": sort_by,
            "limit": safe_limit,
        }
    if name == "get_product_details":
        product_id = result.product_id if isinstance(result, ProductLookupResult) else None
        return {"product_id": product_id or "[unmatched reference omitted]"}
    if name == "lookup_inventory":
        if isinstance(result, InventoryLookupResult):
            return {
                "product_id": result.product_id,
                "size": _known_size(ctx, result.requested_size) or "[unlisted size omitted]",
            }
        return {"product_id": "[unmatched reference omitted]", "size": _known_size(ctx, values.get("size"))}
    return {}


def _safe_result(name: str, result: Any, ctx: Any) -> dict[str, Any]:
    if result is None:
        return {"status": "not_found"}
    if name == "search_catalogue" and isinstance(result, list):
        products = [item for item in result if isinstance(item, ProductLookupResult)]
        return {
            "status": "returned",
            "match_count": len(products),
            "matches": [
                {"product_id": item.product_id, "name": _short(item.name, 70), "price": item.price}
                for item in products[:3]
            ],
        }
    if name == "get_product_details" and isinstance(result, ProductLookupResult):
        return {
            "status": "found",
            "product_id": result.product_id,
            "name": _short(result.name, 70),
            "price": result.price,
        }
    if name == "lookup_inventory" and isinstance(result, InventoryLookupResult):
        return {
            "status": "returned",
            "product_id": result.product_id,
            "product_name": _short(result.product_name, 70),
            "requested_size": _known_size(ctx, result.requested_size) or ("[unlisted size omitted]" if result.requested_size else None),
            "sizes": [
                {"size": _known_size(ctx, item.size) or "[unlisted size omitted]", "quantity": item.quantity, "in_stock": item.in_stock}
                for item in result.sizes[:8]
            ],
        }
    return {"status": "returned"}


def _record_tool(name: str, bound: inspect.BoundArguments, result: Any, ctx: Any) -> None:
    events = _CURRENT_RUN.get()
    if events is None:
        return
    events.append({
        "time": _timestamp(),
        "tool_name": name,
        "arguments": _safe_arguments(name, bound, result, ctx),
        "result": _safe_result(name, result, ctx),
    })


def _record_tool_error(name: str, bound: inspect.BoundArguments, error: Exception, ctx: Any) -> None:
    events = _CURRENT_RUN.get()
    if events is None:
        return
    events.append({
        "time": _timestamp(),
        "tool_name": name,
        "arguments": _safe_arguments(name, bound, None, ctx),
        "result": {"status": "error", "error_type": type(error).__name__},
    })


def audited_tool(function: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a sync PydanticAI tool while retaining its signature and documentation."""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind_partial(*args, **kwargs)
        ctx = bound.arguments.get("ctx")
        try:
            result = function(*args, **kwargs)
        except Exception as error:
            _record_tool_error(function.__name__, bound, error, ctx)
            raise
        _record_tool(function.__name__, bound, result, ctx)
        return result

    return wrapper


def begin_agent_audit() -> Token[list[dict[str, Any]] | None]:
    return _CURRENT_RUN.set([])


def _append_json_array(entries: list[dict[str, Any]]) -> None:
    """Append entries at the closing bracket without rewriting prior JSON records."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(AUDIT_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with os.fdopen(descriptor, "r+b", closefd=False) as trail:
            trail.seek(0)
            raw = trail.read()
            if raw.strip():
                previous = json.loads(raw.decode("utf-8"))
                if not isinstance(previous, list) or any(not isinstance(item, dict) for item in previous):
                    raise ValueError("The agent audit trail must contain a JSON array of entries.")
            else:
                previous = []
                raw = b"[\n]\n"
                trail.seek(0)
                trail.write(raw)
                trail.flush()

            closing_bracket = raw.rstrip().rfind(b"]")
            if closing_bracket < 0:
                raise ValueError("The agent audit trail JSON array is incomplete.")
            prefix = raw[:closing_bracket].rstrip()
            trail.seek(len(prefix))
            trail.truncate()
            if previous:
                trail.write(b",\n  ")
            else:
                trail.write(b"\n  ")
            serialized = [json.dumps(entry, ensure_ascii=False, separators=(",", ":")) for entry in entries]
            trail.write(b",\n  ".join(item.encode("utf-8") for item in serialized))
            trail.write(b"\n]\n")
            trail.flush()
            os.fsync(descriptor)
        os.chmod(AUDIT_PATH, 0o600)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def finish_agent_audit(
    token: Token[list[dict[str, Any]] | None],
    *,
    stop_reason: str,
    result_summary: dict[str, Any],
) -> None:
    events = _CURRENT_RUN.get() or []
    stop_reason = _short(stop_reason, 120)
    entries = [
        {**event, "agent_stop_reason": stop_reason}
        for event in events
    ]
    entries.append({
        "time": _timestamp(),
        "tool_name": "agent_run",
        "arguments": {"tool_calls": len(events)},
        "result": result_summary,
        "agent_stop_reason": stop_reason,
    })
    try:
        _append_json_array(entries)
    finally:
        _CURRENT_RUN.reset(token)
