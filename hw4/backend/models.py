"""Request and response models for the Campus Customs chat API."""

from typing import Literal

from pydantic import BaseModel, Field


class StockOption(BaseModel):
    size: str
    quantity: int


class ProductCard(BaseModel):
    product_id: str
    name: str
    garment_type: str
    description: str
    colors: list[str]
    search_tags: list[str]
    image_url: str
    price: float
    sizes: list[StockOption] = Field(default_factory=list)


class ProductMatch(BaseModel):
    """Compact, clickable catalogue match returned alongside a chat reply."""

    product_id: str
    name: str
    garment_type: str
    image_url: str
    price: float
    short_description: str
    sizes: list[StockOption] = Field(default_factory=list)


class ProductLookupResult(BaseModel):
    """Catalogue data returned by product search and detail lookups."""

    product_id: str
    name: str
    garment_type: str
    description: str
    colors: list[str]
    search_tags: list[str]
    image_url: str
    price: float


class InventorySizeResult(BaseModel):
    """Stock quantity for a single product size."""

    size: str
    quantity: int = Field(ge=0)
    in_stock: bool


class InventoryLookupResult(BaseModel):
    """Inventory rows for one catalogue product, optionally narrowed to one requested size."""

    product_id: str
    product_name: str
    requested_size: str | None = None
    sizes: list[InventorySizeResult] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class PageContext(BaseModel):
    page_type: Literal["home", "products", "product_detail", "about", "login", "create_account", "other"] = "other"
    path: str = Field(default="/", max_length=300)
    product_id: str | None = Field(default=None, max_length=160)
    product_name: str | None = Field(default=None, max_length=200)


class AgentCustomer(BaseModel):
    """Authenticated customer details intentionally made available to the agent."""

    name: str = Field(min_length=1, max_length=161)
    email: str = Field(min_length=3, max_length=254)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    page_context: PageContext = Field(default_factory=PageContext)


class AgentAnswer(BaseModel):
    """Structured model output; product IDs are checked against SQLite by the API."""

    reply: str = Field(min_length=1, max_length=2400)
    product_ids: list[str] = Field(default_factory=list, max_length=8)


class ChatReply(BaseModel):
    reply: str
    products: list[ProductMatch] = Field(default_factory=list)


class ChatHistoryMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    products: list[ProductMatch] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    authenticated: bool
    messages: list[ChatHistoryMessage] = Field(default_factory=list)
