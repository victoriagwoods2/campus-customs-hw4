# AI Prompts

## Problem 1: Prompt tracking setup

**First prompt:** Create `AI_prompts.md` to track the prompts I use during the assignment. Add a numbered, titled section for each problem. Record my prompts in my own words, and if I give a follow-up, include it along with one sentence explaining what was still missing after the first prompt. Start with this request as the Problem 1 prompt and keep updating the file as we work without inventing prompts or follow-ups.

## Problem 2: Database schema and field guide

**First prompt:** Inspect `data/campus_customs.db` and document the fields in `catalogue`, `inventory`, and `users`, with a short explanation of each field's purpose for the shop or chatbot. Create or update `output/harness.md` and leave the database unchanged.

## Problem 3: Campus Customs storefront and API

**First prompt:** Build an initial Campus Customs site with React, Vite, and TypeScript, including Home, Products, About Us, Log in, and Create account pages. Use the supplied style notes to guide original copy and design. List catalogue products with images, names, prices, and short descriptions; give each product a detail page with a large image, full description, price, and sizes and stock when available. Add a bottom-right chat placeholder and a basic FastAPI product and image API in `backend/main.py`.

**Follow-up prompt:** Research the Campus Customs site online to understand its brand, products, and style, then write original Home and About Us copy in your own voice without copying. Keep the requested catalogue, product detail, navigation, chat placeholder, and FastAPI features, and record this follow-up.

**What was still missing after the first prompt:** The style notes were only a placeholder, so the first prompt did not supply researched brand, product, or style context for the Home and About Us copy.

## Problem 4: Account creation and login

**First prompt:** Add account registration and login to the existing Campus Customs site and FastAPI backend using the existing `users` table structure. Collect first name, last name, email, password, and confirmation when registering, and email and password when logging in. Store accounts with securely hashed passwords, use the seeded assignment account ([test password: REDACTED]) and a newly created account to check both flows, and document stored user information and password protection in `output/harness.md`. Keep the test password out of committed files.

## Problem 5: PydanticAI shop assistant

**First prompt:** Connect the Campus Customs chat widget to a PydanticAI agent served by FastAPI while preserving product and account features. Organize the backend into `main.py`, `agent.py`, `tools.py`, and `models.py`, and store the system prompt and voice and safety guidance in `backend/prompts/prompt.md`. Have the frontend send chat messages to FastAPI and display replies with matching product cards. Use catalogue and inventory data for accurate product, price, size, and stock answers. Load the model key from a local environment variable, support startup from `backend/` with `uvicorn main:app --reload --port 8000`, explain prompt/model loading and chat request/response flow in `output/harness.md`, and record this prompt here.

## Problem 6: database-backed product and inventory tools

**First prompt:** Add agent tools for looking up product descriptions and prices and inventory by size in `data/campus_customs.db`, using the actual schema fields. Require the agent to use these lookups for product questions, never guess prices or stock, and clearly say when a requested size is out of stock. Update `backend/prompts/prompt.md` with tool-use guidance, add Pydantic return types in `backend/models.py`, document each tool's returned fields and their usefulness in `output/harness.md`, and test the tools with real database entries.

## Problem 7: catalogue matches in chat

**First prompt:** Let shoppers ask for product types such as hoodies and have the agent search the catalogue for matching items. Return structured matches alongside the chat reply, including an image, name, price, short description, and the ID needed for the product detail route. Display those matches as clickable product cards in the chat, update the prompt and Pydantic response types, and add this prompt here.

## Problem 8: saved chat history and request context

**First prompt:** Save chat history for logged-in users in the database and reload it when they return; keep guest chat available without saving guest history. Scope stored messages so each user can see only their own. Pass the authenticated customer's name and email to the agent from the backend, and include current page context, especially the product ID or name on a product page, so it can resolve follow-up questions such as asking whether “this” comes in pink. Document the history storage, customer fields, and page context flow in `output/harness.md`, and add this prompt here.

## Problem 9: usability and agent improvements

**First prompt:** Review the Campus Customs app and choose exactly two front-end improvements for usability or appearance and exactly two agent or backend improvements for usefulness, accuracy, safety, speed, or cost. Implement the four changes while keeping shop features working. Create `output/usability.md` explaining what each change adds and why it helps shoppers or the business. Run the app, check all four improvements, confirm the write-up matches them, and add this prompt here.

## Problem 10: Campus Customs storefront redesign

**First prompt:** Redesign the existing Campus Customs site as a distinctive, polished storefront. Make coordinated choices for typography, color, visual hierarchy, motion, product presentation, and chat, and apply the design throughout the running site rather than a mockup. Keep it usable on mobile and preserve the existing shop features. Create `output/design.md` with concrete design changes and how they may encourage browsing and shopping, and add this prompt here.

## Problem 11: live shop checks and screenshots

**First prompt:** Run the Campus Customs app and check three things with the real database and working features: ask the chatbot for a product's price and stock and capture its database-based answer; ask for a category such as hoodies and capture the matching product cards on the page; and use a Problem 9 usability improvement and capture it working. Save genuine screenshots in `output/app_check_images/` and create `output/app_check.html` with a heading, screenshot, and brief explanation for each check, using relative image paths. Do not fabricate screenshots or results; if a check cannot be run or captured, explain the blocker and what is needed for the missing screenshot.

## Problem 12: agent audit trail and system documentation

**First prompt:** Add an append-only `output/audit_trail.json` for agent-loop activity. Record each activity's time, tool name, short sanitized arguments and result, and why the agent stopped; preserve earlier entries and never log passwords, API keys, tokens, or full private chat histories. Add safety rules to `backend/prompts/prompt.md` requiring database-backed price and stock answers, clear unavailable notices, customer privacy, and no unverified claims about facts or actions. Finish `output/harness.md` from the implemented code, covering every model field and purpose, agent tools and abilities, safety rules, actual loop and result limits, models, and run commands. Add this prompt here.

## Problem 13: package and publish the finished project

**First prompt:** Prepare the finished assignment in a top-level `hw4/` folder with the frontend, backend, prompt log, requirements, placeholder-only `.env.example`, `.gitignore`, and a README explaining how to run both apps and install the local data pack. Keep all requested agent files under `backend/` and the harness, design, usability, app-check page and images, and sanitized audit trail under `output/`. Keep the database, product images, secrets, passwords, and private customer data out of GitHub, but retain the required screenshots and sanitized audit evidence. Review the exact publishable files, then create or use a public GitHub repository, push the project without a zip, and give me its cloneable URL. If sign-in or another user action is required, tell me exactly what to do.
