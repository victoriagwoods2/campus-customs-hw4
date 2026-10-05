# Problem 9: usability improvements

I reviewed the shop and selected two storefront improvements and two agent/backend improvements.

## Front end

### 1. Sort the product collection

The Products page now lets shoppers sort the filtered catalogue by price (low to high or high to low) and name, while keeping the original featured order available. This makes it easier to compare items and find an option that fits a shopper's budget.

### 2. Add suggested chat questions

The chat panel now shows one-tap starter questions while a conversation is new. On a product detail page, the suggestions ask about that item; elsewhere, they help shoppers discover garment types, compare lower prices, or check a size. This gives shoppers a clear first step and uses the existing page context for product follow-ups.

## Agent and backend

### 3. Bound the chat context and generated answer size

Before a chat request reaches the model, the backend keeps the newest conversation text within a 6,000-character context budget, preserving the latest customer message and removing older context first. Each model response also has a 700-token output cap. This limits unnecessary prompt and completion usage while retaining recent context for follow-up questions.

### 4. Use catalogue filters for budget and availability requests

The agent prompt now explicitly tells the agent to pass budget ceilings to catalogue search, sort cheapest-item requests by price, and use size and in-stock filters when finding available items. Exact stock and quantity questions still use the inventory lookup. This encourages answers to be based on matching database records instead of broad or unfiltered search results.

## Verification

The storefront production build and backend Python compilation completed. I ran the storefront on port 5173 and the API on port 8001 because port 8000 was already occupied. The running storefront served its updated Vite module, and the catalogue API returned 102 products. I exercised the actual product-sorting helper for price, name, and featured order, and checked that the served chat UI contains clickable suggestions for both general and product-page contexts.

I also called the chat route with a local stub agent and a full history payload: the latest product question and product-page context were preserved, the model settings included the per-response 700-token cap, and the submitted prompt stayed within 6,000 characters. This did not make a live model request. Finally, the budget and in-stock size filters returned matching records from the real SQLite catalogue and inventory, and the agent prompt contains the corresponding tool-use guidance.
