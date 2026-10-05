# Campus Customs

A React, Vite, and TypeScript storefront with a FastAPI backend and a PydanticAI shopping assistant. The catalogue database and product images are a separate local data pack and are intentionally not included in this repository.

The assignment project lives in the repository's `hw4/` folder. After cloning, change into that folder before running the setup commands below:

```bash
cd campus-customs-hw4/hw4
```

If you are already at the repository root, use `cd hw4` instead.

You need Python 3.10 or newer, Node.js 18 or newer, and npm.

## Install the local data pack

After cloning this project, obtain the assignment's `data.zip` separately. From the `hw4/` project folder, extract it so the resulting paths are exactly:

```text
data/campus_customs.db
data/products/
```

For example, if `data.zip` is in your Downloads folder:

```bash
unzip ~/Downloads/data.zip -d .
```

Check that `data/campus_customs.db` exists and that `data/products/` contains the catalogue images before starting the apps. The local `data/` folder, database, image files, and zip are ignored by Git.

## Configure local environment

From the `hw4/` folder, make a private local environment file from the example:

```bash
cp .env.example .env
```

Edit `.env` and set `PORTKEY_API_KEY` to your own key for chatbot use. Replace `CAMPUS_CUSTOMS_SESSION_SECRET` with a long random value to keep signed-in sessions stable across API restarts. For HTTPS production hosting, set `APP_ENV=production` in `.env` to mark the session cookie secure. These values are local only; never commit `.env`.

## Run the FastAPI backend

From the `hw4/` folder, create and activate the project virtual environment and install the Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then start the API from `backend/` as required by the app configuration:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API documentation is available at `http://localhost:8000/docs`.

## Run the React frontend

In a second terminal, from `hw4/`:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). The Vite development server forwards `/api` requests to FastAPI at `http://127.0.0.1:8000`.

## Project files

- `frontend/` contains the React, TypeScript, and Vite storefront.
- `backend/` contains the FastAPI routes, PydanticAI agent, models, database tools, audit writer, and system prompt.
- `output/` contains the system guide, design and usability notes, Problem 11 app-check report and screenshot folder, and append-only sanitized agent audit trail.
- `AI_prompts.md` records the assignment prompts.

The chatbot needs `PORTKEY_API_KEY`; the shop catalogue and account features need the separately supplied local data pack. Audit records are written to `output/audit_trail.json` when chat requests run. The audit log omits chat text, customer identity, credentials, API keys, and tokens.
