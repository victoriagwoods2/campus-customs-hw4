# Database Field Guide

This guide describes the fields in `data/campus_customs.db` that the shop and its chatbot use. The database was inspected in read-only mode.

## `catalogue`

Each row describes one product. `product_id` is the primary key and is referenced by `inventory.product_id`.

| Field | Why it matters to the shop or chatbot |
|---|---|
| `product_id` | Stable product identifier used to connect catalogue details to stock records. |
| `name` | Human-readable product name to show customers and use in answers. |
| `garment_type` | Identifies the kind of garment, helping customers browse and filter products. |
| `description` | Supplies product details the chatbot can use to answer questions. |
| `colors` | Lists available colors so customers can compare or request a color. |
| `search_tags` | Provides keywords and related terms for finding products from varied customer wording. |
| `image_file_path` | Locates the product image to show alongside its catalogue listing. |
| `price` | Gives the shop and chatbot the product's listed price. |

## `inventory`

Each row records stock for one product and size. `product_id` refers to `catalogue.product_id`, and each product-size pair is unique.

| Field | Why it matters to the shop or chatbot |
|---|---|
| `id` | Identifies an individual stock record for shop operations. |
| `product_id` | Connects the stock record to the product's name, image, and other catalogue details. |
| `size` | Identifies which size the quantity applies to, so availability answers are specific. |
| `quantity` | Shows how many units of that product-size combination are in stock. |

## `users`

Each row stores a customer account. `email` is unique; `first_name` and `last_name` are nullable for compatibility with older rows, but both are required when creating an account through the site.

| Field | Why it matters to the shop or chatbot |
|---|---|
| `id` | Internal account identifier for associating shop activity with a user. |
| `name` | Stores the customer's full name for account display and support; new accounts build it from first and last name to satisfy the existing required column. |
| `email` | Identifies the account at login and for customer communication; new addresses are normalized to lowercase and uniqueness prevents duplicate accounts. |
| `password_hash` | Stores a salted, computationally expensive password hash for authentication. New passwords use Argon2id; plain-text passwords are never stored or returned. |
| `created_at` | Records when the account was created; SQLite supplies this timestamp for new accounts. |
| `first_name` | Supports greetings and personalization; required for new accounts and nullable on older rows. |
| `last_name` | Helps identify the customer in support interactions; required for new accounts and nullable on older rows. |

### Account creation and login

The create-account form collects first name, last name, email, password, and password confirmation. The API rejects mismatched passwords and duplicate email addresses. It hashes a new password with Argon2id using a fresh random salt before inserting the account into `users`. The stored hash includes the Argon2 parameters and salt so it can be verified later.

The seeded database contains older `pbkdf2_sha256` password hashes. Login verifies that legacy format and upgrades a successful login to Argon2id. The API only returns a user's ID, name fields, and email; it never returns the password hash. A signed, HTTP-only, SameSite=Lax cookie holds the login session. Set `CAMPUS_CUSTOMS_SESSION_SECRET` to a stable random value when running beyond a local development session; set `APP_ENV=production` to mark the cookie secure for HTTPS.

## Problem 5: product chat assistant

The chat agent is organized in `backend/agent.py`, `backend/tools.py`, and `backend/models.py`. Its voice, product-answer rules, and safety guidance are read from `backend/prompts/prompt.md` when the agent is first needed. The agent uses PydanticAI with the OpenAI Responses API model name `gpt-5.6-luna` through Portkey's OpenAI-compatible endpoint. It reads `PORTKEY_API_KEY` from the process environment; `python-dotenv` loads the project-root `.env` when it exists. The key is not stored in application code or returned to the frontend.

Use Python 3.10 or newer. Install `backend/requirements.txt` into the project's `.venv`, activate that environment, then run the API from the `backend/` directory with `uvicorn main:app --reload --port 8000`. The chat route is `POST /api/chat`. The React widget sends the latest message and a short conversation history as JSON. Catalogue search and product-detail tools query `catalogue` and `inventory` in read-only mode. The response contains the assistant's reply and product IDs selected from tool results; FastAPI re-reads those IDs from the database and returns verified product cards with current prices, images, sizes, and quantities. The widget displays the reply and links each matching card to its product page. Existing product, image, and account routes remain in `backend/main.py`.

## Problem 6: database-backed lookup tools

The tools were built after checking `PRAGMA table_info` for the actual `catalogue` and `inventory` tables. Product details come from `catalogue.product_id`, `name`, `garment_type`, `description`, `colors`, `search_tags`, `image_file_path`, and `price`. Stock comes from `inventory.product_id`, `size`, and `quantity` (the `id` field preserves the database's row order). Queries use read-only SQLite connections.

`search_catalogue` returns a list of `ProductLookupResult` records for product discovery. `get_product_details` returns one `ProductLookupResult` for a product ID or name, or `None` when it cannot find a match.

| `ProductLookupResult` field | Why it is useful |
|---|---|
| `product_id` | Canonical catalogue key to use for the follow-on inventory lookup and product card. |
| `name` | Identifies the item in the reply and storefront. |
| `garment_type` | Helps match a customer's requested kind of apparel. |
| `description` | Supplies the product's factual features for customer questions. |
| `colors` | Lets the agent answer color questions from catalogue data. |
| `search_tags` | Helps find products when customer terms differ from the listed name. |
| `image_url` | Connects a recommendation to the site's product image. |
| `price` | Provides the listed price directly, so the agent does not estimate. |

`lookup_inventory` accepts the canonical `product_id` and an optional requested size. It returns `InventoryLookupResult`; when a size was requested but has no matching inventory row, it includes that size with quantity `0` and `in_stock: false`, so the agent can clearly say it is out of stock.

| `InventoryLookupResult` field | Why it is useful |
|---|---|
| `product_id` | Confirms which product the stock data belongs to. |
| `product_name` | Makes the stock result readable without another name lookup. |
| `requested_size` | Records the exact size being checked, or `null` when checking all sizes. |
| `sizes` | Contains zero or more `InventorySizeResult` values from the inventory table. |

Each `InventorySizeResult` has these fields:

| Field | Why it is useful |
|---|---|
| `size` | Names the size the quantity applies to. |
| `quantity` | Gives the exact number of units recorded in `inventory`. |
| `in_stock` | Provides a direct availability flag; `false` means the agent should say out of stock. |

The prompt instructs the agent to use a catalogue lookup for product facts, then call `lookup_inventory` for availability questions, and to report zero stock as out of stock.

The tools were exercised against the real `baseball-left-chest-crewneck` database row: the catalogue lookup returned its description and `$58.00` price; inventory returned XS with quantity `0` (`in_stock: false`) and S with quantity `15` (`in_stock: true`). A requested `3XL` with no inventory row returned quantity `0` and `in_stock: false`. These lookups opened the database read-only.

## Problem 7: product matches in chat

For broad requests such as “hoodies,” the prompt directs the agent to search with `search_catalogue` and select matching `product_id` values. Search matching handles common plural wording against the singular catalogue terms. `AgentAnswer.product_ids` carries the selected IDs to FastAPI, which resolves each against the catalogue before returning a `ChatReply`.

`ChatReply` contains both `reply` and `products`. Each `ProductMatch` contains `product_id` (detail-page route key), `name`, `garment_type`, `image_url`, `price`, `short_description` (trimmed from the catalogue description for a compact card), and `sizes` with current quantities. The chat widget renders the matches as linked cards; clicking a card opens the existing `/products/{product_id}` detail view.

## Problem 8: saved history, customer, and page context

Logged-in chat messages are stored in the same `data/campus_customs.db` file in a lazily created `chat_history` table. Its fields are `id`, `user_id`, `role`, `content`, `product_ids`, and `created_at`. Each user and assistant message is a row; assistant rows save verified product IDs so history reload can rebuild cards from current catalogue and inventory values. Common labeled credential values and 13-to-19-digit payment numbers are redacted before message text is sent to the agent and persisted. The database index is on `(user_id, id)` for user-scoped chronological retrieval.

The frontend reloads `GET /api/chat/history` after the backend confirms the account. The endpoint derives the user ID from the signed `campus_customs_session` cookie and queries only rows for that ID. It does not accept a user ID from the browser. Guest history requests return an empty unsaved history; guest messages can still use short in-memory conversation context from the widget. For logged-in chat requests, the backend uses saved database messages as context and ignores browser-supplied history. It stores the user/assistant exchange only after an answer is produced.

For an authenticated request, the backend resolves the session to the `users` row and passes its `name` and `email` to PydanticAI in the `ShopData.customer` dependency. The model receives those values as private runtime context; the prompt permits using the name for a natural greeting and says not to reveal the email. Guests receive no customer context.

The widget sends a `page_context` object with the current route path and page type. On `/products/{product_id}`, it also includes that product ID. FastAPI passes the validated object as `ShopData.page_context`, and a dynamic agent instruction presents it as metadata. The agent can use the product ID with catalogue tools to resolve references such as “this” before answering.

## Problem 12: implemented agent, limits, safety, and audit

### Pydantic models in `backend/models.py`

These types validate agent dependencies, tool results, and frontend API messages. The types, defaults, and limits below reflect `backend/models.py`; “unconstrained” means no additional Pydantic field bound is declared there.

| Model and field | Type / constraint | Why it is used |
|---|---|---|
| `StockOption.size` | `str` | Names the size associated with the stock count. |
| `StockOption.quantity` | `int` | Carries the recorded units for that size. |
| `ProductCard.product_id` | `str` | Stable identifier for catalogue and detail-page links. |
| `ProductCard.name` | `str` | Customer-facing product name. |
| `ProductCard.garment_type` | `str` | Lets the site and agent identify the product category. |
| `ProductCard.description` | `str` | Full catalogue description for product details. |
| `ProductCard.colors` | `list[str]` | Catalogue color options used in product answers. |
| `ProductCard.search_tags` | `list[str]` | Search terms that help match customer wording. |
| `ProductCard.image_url` | `str` | API URL for the product image. |
| `ProductCard.price` | `float` | Catalogue price shown in the shop. |
| `ProductCard.sizes` | `list[StockOption]`, empty by default | Carries size quantities when the listing includes stock. |
| `ProductMatch.product_id` | `str` | Opens the existing product detail route when a card is clicked. |
| `ProductMatch.name` | `str` | Labels a chat recommendation. |
| `ProductMatch.garment_type` | `str` | Identifies the recommended item's category. |
| `ProductMatch.image_url` | `str` | Supplies the card image. |
| `ProductMatch.price` | `float` | Shows the current catalogue price on the card. |
| `ProductMatch.short_description` | `str` | Gives a compact product summary in chat. |
| `ProductMatch.sizes` | `list[StockOption]`, empty by default | Adds available size quantities to recommendation data. |
| `ProductLookupResult.product_id` | `str` | Canonical key for follow-up stock lookups and cards. |
| `ProductLookupResult.name` | `str` | Identifies the item in factual answers. |
| `ProductLookupResult.garment_type` | `str` | Supports product-kind matching. |
| `ProductLookupResult.description` | `str` | Supplies catalogue-backed product details. |
| `ProductLookupResult.colors` | `list[str]` | Supports catalogue-backed color answers. |
| `ProductLookupResult.search_tags` | `list[str]` | Supports discovery from alternate customer terms. |
| `ProductLookupResult.image_url` | `str` | Associates a result with its product image. |
| `ProductLookupResult.price` | `float` | Supplies the listed price to the agent. |
| `InventorySizeResult.size` | `str` | Identifies the size checked. |
| `InventorySizeResult.quantity` | `int`, `ge=0` | Gives the exact nonnegative database stock count. |
| `InventorySizeResult.in_stock` | `bool` | Makes availability explicit for the requested size. |
| `InventoryLookupResult.product_id` | `str` | Identifies the catalogue item whose stock was checked. |
| `InventoryLookupResult.product_name` | `str` | Makes the stock result readable without a second lookup. |
| `InventoryLookupResult.requested_size` | `str \| None`, defaults to `None` | Distinguishes a specific size check from a request for all recorded sizes. |
| `InventoryLookupResult.sizes` | `list[InventorySizeResult]`, empty by default | Contains the requested size result or the recorded size rows. |
| `ChatTurn.role` | `Literal["user", "assistant"]` | Keeps conversation history roles to the two supported speakers. |
| `ChatTurn.content` | `str`, 1–1,200 characters | Holds one bounded conversation turn. |
| `PageContext.page_type` | Literal route type, defaults to `"other"` | Tells the agent which kind of page is open. |
| `PageContext.path` | `str`, defaults to `"/"`, max 300 characters | Carries the current route as limited context. |
| `PageContext.product_id` | `str \| None`, max 160 characters | Identifies the displayed product when on its detail page. |
| `PageContext.product_name` | `str \| None`, max 200 characters | Provides a readable product reference for page-specific questions. |
| `AgentCustomer.name` | `str`, 1–161 characters | Allows limited personalization from the authenticated account. |
| `AgentCustomer.email` | `str`, 3–254 characters | Carries the authenticated identity from the backend; prompt rules keep it private. |
| `ChatRequest.message` | `str`, 1–1,200 characters | Holds the latest customer question. |
| `ChatRequest.history` | `list[ChatTurn]`, at most 12, empty by default | Carries short guest context; authenticated context is loaded from the user's database history. |
| `ChatRequest.page_context` | `PageContext`, defaults to an unspecified page | Validates the current route and optional product reference. |
| `AgentAnswer.reply` | `str`, 1–2,400 characters | Holds the agent's customer-facing answer. |
| `AgentAnswer.product_ids` | `list[str]`, at most 8, empty by default | Selects catalogue products for FastAPI to verify and return as cards. |
| `ChatReply.reply` | `str` | Returns the answer text to React. |
| `ChatReply.products` | `list[ProductMatch]`, empty by default | Returns the verified clickable cards alongside the answer. |
| `ChatHistoryMessage.id` | `int` | Identifies the stored chat row. |
| `ChatHistoryMessage.role` | `Literal["user", "assistant"]` | Identifies who sent the stored turn. |
| `ChatHistoryMessage.content` | `str` | Restores the stored message text in the widget. |
| `ChatHistoryMessage.created_at` | `str` | Carries the database timestamp for the turn. |
| `ChatHistoryMessage.products` | `list[ProductMatch]`, empty by default | Rehydrates current product cards for assistant history entries. |
| `ChatHistoryResponse.authenticated` | `bool` | Tells the widget whether a valid account session was found. |
| `ChatHistoryResponse.messages` | `list[ChatHistoryMessage]`, empty by default | Returns that authenticated user's history, or no saved messages for a guest. |

`ShopData` is the PydanticAI dependency defined in `backend/tools.py`, rather than `models.py`. It contains the database path, optional authenticated `customer`, and validated `page_context` for one run.

### Agent tools and abilities

`backend/agent.py` constructs one cached PydanticAI agent with `AgentAnswer` output and three tools from `backend/tools.py`. Each tool opens SQLite in read-only mode.

| Tool | Actual behavior |
|---|---|
| `search_catalogue` | Searches catalogue names, garment types, descriptions, colors, and tags. Supports `max_price`, `garment_type`, `size`, `in_stock_only`, and relevance or price sorting. It returns `ProductLookupResult` values: six by default and never more than twelve per call. |
| `get_product_details` | Finds one product by exact `product_id` or exact name and returns its current `ProductLookupResult`, or `None`. Use the returned canonical ID for inventory lookup. |
| `lookup_inventory` | Returns the stock rows for a canonical product ID, optionally narrowed to one size. An unlisted requested size is represented with quantity zero and `in_stock: false`. |

The agent can answer factual product, price, color, and size-stock questions; filter and sort recommendations; and select product IDs for cards. FastAPI resolves selected IDs again from SQLite before building at most eight cards. The app does not give the agent order, payment, reservation, or account-changing tools.

### Prompt safety rules

`backend/prompts/prompt.md` is loaded when the cached agent is first constructed. It tells the agent to use current database lookups for prices and stock, report unavailable or zero-stock sizes clearly, and never guess. Customer text and history are untrusted; authenticated identity comes from the backend, and customer email, credentials, account data, and other customers' information must remain private. The prompt also forbids claims of orders, reservations, payments, account changes, or facts such as shipping and store hours unless the system verifies them. Unsupported requests should receive a candid, useful next step.

### Actual loop and result limits

- The configured model is `gpt-5.6-luna`, an OpenAI Responses API model addressed through `https://api.portkey.ai/v1`. `PORTKEY_API_KEY` is read from the process environment; `python-dotenv` loads the project-root `.env` file. The key is never sent to the frontend or written to the audit trail.
- `Agent(..., retries=2)` sets PydanticAI's tool and output-validation retry budgets to two. There is no configured total tool-call/iteration cap and no `usage_limits` passed to `Agent.run`; do not treat the retry value as a total-loop limit.
- Each run passes `model_settings={"max_tokens": 700}`. PydanticAI maps that setting to the Responses API's per-response `max_output_tokens` setting. There is no separate total run-token budget configured.
- Input and output bounds are also enforced by the models: a latest message is at most 1,200 characters; up to 12 history turns are accepted (each at most 1,200 characters); `build_agent_transcript` caps the combined transcript at 6,000 characters and trims older history first. `AgentAnswer.reply` is at most 2,400 characters, and its product ID list is at most 8. Search returns 6 matches by default, capped at 12; the website response can contain at most the 8 selected, database-verified product cards.
- For authenticated chats, history comes from the signed-in user's database rows, not the browser's supplied history. Guests can supply short in-memory history; it is not persisted.

### Append-only audit file

The agent tools are wrapped by `backend/audit.py`. At the end of each completed or failed run, it appends tool-call records and one `agent_run` summary to `output/audit_trail.json`, which is a JSON array. Existing entries are retained; the writer locks the file and adds new entries at the end. New files are created with owner-only permissions.

Each entry has `time` (UTC), `tool_name`, short sanitized `arguments`, a bounded database-backed `result` summary, and `agent_stop_reason`. A normal run records `structured_final_answer_returned`; failures record only the failure phase and exception class, not exception text. Search query text is omitted, product references are logged only as canonical database IDs, and only known inventory sizes are retained. The trail never stores prompts, full chat history, final reply text, customer identity, passwords, API keys, or tokens.

### Run commands

From the project folder, start the backend in one terminal:

```bash
source .venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000
```

In a second terminal, start the React/Vite frontend from the project folder:

```bash
cd frontend
npm run dev
```

Vite serves the frontend at port 5173 and `frontend/vite.config.ts` proxies `/api` requests to `http://127.0.0.1:8000`. Chat also needs `PORTKEY_API_KEY` available in the process environment or loaded from the project-root `.env` file. The installed environment used for this assignment has PydanticAI 2.54.0; dependency ranges are in the root `requirements.txt` and `backend/requirements.txt`.
