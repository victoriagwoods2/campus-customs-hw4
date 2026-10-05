"""Read-only catalogue and inventory tools exposed to the shop assistant."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

try:
    from .models import (
        AgentCustomer,
        InventoryLookupResult,
        InventorySizeResult,
        PageContext,
        ProductCard,
        ProductLookupResult,
        StockOption,
    )
except ImportError:  # Support `uvicorn main:app` from the backend/ directory.
    from models import AgentCustomer, InventoryLookupResult, InventorySizeResult, PageContext, ProductCard, ProductLookupResult, StockOption


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "campus_customs.db"
STOP_WORDS = {
    "a", "an", "and", "are", "any", "about", "available", "can", "do", "does",
    "for", "have", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or",
    "please", "show", "tell", "the", "there", "to", "we", "what", "which", "with",
    "affordable", "below", "cheapest", "cheap", "cost", "costs", "in-stock", "less",
    "lowest", "price", "prices", "size", "stock", "than", "under", "unavailable",
    "availability", "item", "items", "product", "products", "xs", "xl", "xxl",
}


class ShopData(BaseModel):
    database_path: Path = DATABASE_PATH
    customer: AgentCustomer | None = None
    page_context: PageContext = Field(default_factory=PageContext)


def _connect(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise RuntimeError("The Campus Customs catalogue database is unavailable.")
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value] if value else []
    return parsed if isinstance(parsed, list) else []


def _product_card(row: sqlite3.Row, sizes: list[sqlite3.Row]) -> ProductCard:
    image_name = Path(row["image_file_path"]).name
    return ProductCard(
        product_id=row["product_id"],
        name=row["name"],
        garment_type=row["garment_type"],
        description=row["description"],
        colors=_parse_list(row["colors"]),
        search_tags=_parse_list(row["search_tags"]),
        image_url=f"/api/images/{quote(image_name)}",
        price=float(row["price"]),
        sizes=[StockOption(size=item["size"], quantity=item["quantity"]) for item in sizes],
    )


def _product_lookup_result(product: ProductCard) -> ProductLookupResult:
    return ProductLookupResult(
        product_id=product.product_id,
        name=product.name,
        garment_type=product.garment_type,
        description=product.description,
        colors=product.colors,
        search_tags=product.search_tags,
        image_url=product.image_url,
        price=product.price,
    )


def _catalogue_result(row: sqlite3.Row) -> ProductLookupResult:
    image_name = Path(row["image_file_path"]).name
    return ProductLookupResult(
        product_id=row["product_id"],
        name=row["name"],
        garment_type=row["garment_type"],
        description=row["description"],
        colors=_parse_list(row["colors"]),
        search_tags=_parse_list(row["search_tags"]),
        image_url=f"/api/images/{quote(image_name)}",
        price=float(row["price"]),
    )


def _load_products(database_path: Path) -> list[ProductCard]:
    with closing(_connect(database_path)) as connection:
        products = connection.execute("SELECT * FROM catalogue ORDER BY rowid").fetchall()
        stock = connection.execute("SELECT product_id, size, quantity FROM inventory ORDER BY id").fetchall()
    by_product: dict[str, list[sqlite3.Row]] = {}
    for item in stock:
        by_product.setdefault(item["product_id"], []).append(item)
    return [_product_card(row, by_product.get(row["product_id"], [])) for row in products]


def _normalized_words(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", text.casefold())
        if word not in STOP_WORDS and not (word.isalpha() and len(word) == 1)
    ]


def _word_matches(word: str, searchable_text: str) -> bool:
    """Match common plural customer wording to catalogue's singular product types."""
    variants = {word}
    if len(word) > 3 and word.endswith("s"):
        variants.add(word[:-1])
    if len(word) > 4 and word.endswith("ies"):
        variants.add(f"{word[:-3]}y")
    return any(variant in searchable_text for variant in variants)


def search_catalogue(
    ctx: RunContext[ShopData],
    query: str,
    max_price: float | None = None,
    garment_type: str | None = None,
    size: str | None = None,
    in_stock_only: bool = False,
    sort_by: Literal["relevance", "price_low_to_high", "price_high_to_low"] = "relevance",
    limit: int = 6,
) -> list[ProductLookupResult]:
    """Search catalogue product descriptions and prices.

    Use this to find products for questions about names, descriptions, colors, garment types,
    and prices. Filters can narrow results by maximum price, garment type, size, and stock.
    Set sort_by to price_low_to_high for cheapest-item questions. For an exact stock answer,
    call lookup_inventory with the returned product_id and the customer's size.

    Args:
        query: Customer wording to match against catalogue names, descriptions, colors, and tags.
        max_price: Optional upper price limit in the database's currency.
        garment_type: Optional apparel kind used to narrow the results.
        size: Optional size constraint used when searching by availability.
        in_stock_only: When true, excludes products with no quantity for the selected size.
        sort_by: Keep relevant matches first or order by catalogue price.
        limit: Maximum number of products to return, capped at twelve.
    """
    products = _load_products(ctx.deps.database_path)
    query_words = set(_normalized_words(query))
    type_words = set(_normalized_words(garment_type or ""))
    size_folded = (size or "").strip().casefold()
    matches: list[tuple[int, int, ProductCard]] = []
    for index, product in enumerate(products):
        if max_price is not None and product.price > max_price:
            continue
        if type_words and not all(
            _word_matches(word, " ".join(_normalized_words(product.garment_type)))
            for word in type_words
        ):
            # Also accept a garment-type phrase found in the product tags or description.
            haystack = " ".join([product.garment_type, product.name, product.description, *product.search_tags]).casefold()
            if not all(_word_matches(word, haystack) for word in type_words):
                continue
        relevant_sizes = [option for option in product.sizes if not size_folded or option.size.casefold() == size_folded]
        if size_folded and not relevant_sizes:
            continue
        if in_stock_only and not any(option.quantity > 0 for option in relevant_sizes):
            continue
        searchable = " ".join([
            product.name,
            product.garment_type,
            product.description,
            *product.colors,
            *product.search_tags,
        ]).casefold()
        score = sum(1 for word in query_words if _word_matches(word, searchable))
        if query_words and score == 0:
            continue
        matches.append((score, index, product))

    if sort_by == "price_low_to_high":
        matches.sort(key=lambda item: (item[2].price, -item[0], item[1]))
    elif sort_by == "price_high_to_low":
        matches.sort(key=lambda item: (-item[2].price, -item[0], item[1]))
    else:
        matches.sort(key=lambda item: (-item[0], item[1]))
    return [
        _product_lookup_result(product)
        for _, _, product in matches[: max(1, min(limit, 12))]
    ]


def get_product_details(
    ctx: RunContext[ShopData], product_id_or_name: str
) -> ProductLookupResult | None:
    """Look up one catalogue product by its exact product ID or exact name.

    Returns the product description, colors, image path, and current catalogue price. Use the
    returned product_id with lookup_inventory for any size availability or stock question. Use
    search_catalogue first when the customer's wording is partial or could match several products.

    Args:
        product_id_or_name: Exact catalogue product ID or exact product name.
    """
    query = product_id_or_name.strip()
    if not query:
        return None
    with closing(_connect(ctx.deps.database_path)) as connection:
        row = connection.execute(
            "SELECT * FROM catalogue WHERE product_id = ? COLLATE NOCASE "
            "OR name = ? COLLATE NOCASE LIMIT 1",
            (query, query),
        ).fetchone()
    return _catalogue_result(row) if row is not None else None


def lookup_inventory(
    ctx: RunContext[ShopData], product_id: str, size: str | None = None
) -> InventoryLookupResult | None:
    """Read stock from inventory for a catalogue product, optionally for one size.

    Pass the canonical product_id returned by search_catalogue or get_product_details. Set size
    to the requested size for a precise answer, or omit it to return every size. If the requested
    size has no inventory row, it is returned with quantity 0 and in_stock false.

    Args:
        product_id: Canonical product ID returned by a catalogue lookup.
        size: Requested size label, such as M or XL; omit it to retrieve all recorded sizes.
    """
    product_id = product_id.strip()
    if not product_id:
        return None
    requested_size = size.strip().upper() if size and size.strip() else None
    with closing(_connect(ctx.deps.database_path)) as connection:
        product = connection.execute(
            "SELECT product_id, name FROM catalogue WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if product is None:
            return None
        if requested_size is None:
            rows = connection.execute(
                "SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY id",
                (product["product_id"],),
            ).fetchall()
            sizes = [
                InventorySizeResult(size=row["size"], quantity=row["quantity"], in_stock=row["quantity"] > 0)
                for row in rows
            ]
        else:
            row = connection.execute(
                "SELECT size, quantity FROM inventory "
                "WHERE product_id = ? AND size = ? COLLATE NOCASE ORDER BY id LIMIT 1",
                (product["product_id"], requested_size),
            ).fetchone()
            quantity = int(row["quantity"]) if row is not None else 0
            actual_size = row["size"] if row is not None else requested_size
            sizes = [InventorySizeResult(size=actual_size, quantity=quantity, in_stock=quantity > 0)]
    return InventoryLookupResult(
        product_id=product["product_id"],
        product_name=product["name"],
        requested_size=requested_size,
        sizes=sizes,
    )
