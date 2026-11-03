# Empório da Música — Customer Service Agent

Text-message customer service agent for the fictional **Empório da Música**, a musical instrument store in Campo Grande/MS, Brazil. This project was built for Artefact's AI Engineer take-home challenge.

The agent always replies in **English**. The source CSVs and the policy manual are in Portuguese; the agent translates the meaning around product names, customer names, store names, and policy section numbers. The web UI, CLI, documentation, and example conversations are also in English.

The agent checks the catalog and orders in SQLite, retrieves rules from the policy manual, and only states a price, stock level, deadline, or order status after calling a tool. The app includes a streaming chat and a read-only operational panel with catalog, orders, policies, data quality, and agent traces.

## Stack

- Python 3.11+
- FastAPI + Jinja2 + HTMX
- SQLite + FTS5
- OpenAI **`gpt-6-luna`** via the **Responses API**
- OpenAI **`text-embedding-3-large`** for semantic policy retrieval
- `numpy` for cosine similarity
- `pdfplumber` only for offline policy extraction
- `tzdata` for the `America/Campo_Grande` timezone on Windows
- FastAPI `0.162.0` and Starlette `1.10.0` are pinned because the template-rendering API is version-sensitive

## How to run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env
# edit .env and fill in OPENAI_API_KEY
```

`.env` holds the model, provider, reasoning effort, embedding dimensions, database path, and server settings. Never commit `OPENAI_API_KEY`.

### 1. Ingestion

```bash
python -m app.data.ingest --reset
```

This command:

- creates the SQLite schema;
- reads the six CSVs from `data/`;
- converts money to integer cents and validates dates, statuses, and foreign keys;
- loads the policy sections from `data/policy_sections.json`;
- generates section embeddings with `text-embedding-3-large` when a key is available;
- builds the FTS5 indexes;
- records data-quality anomalies in `data_quality_issues`.

Without an OpenAI key, or to avoid embedding calls:

```bash
python -m app.data.ingest --reset --skip-embeddings
```

In that mode, policy retrieval uses FTS5 only. The chat still works, but without semantic search.

### 2. Server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Chat: http://127.0.0.1:8000/
- Operational panel: http://127.0.0.1:8000/ops
- Health: http://127.0.0.1:8000/health

On first startup, if the database is empty, the app seeds the CSVs without embeddings. For the full experience, run ingestion first.

### 3. CLI

```bash
python -m app.cli chat
python -m app.cli ask "Which acoustic guitars do you have under R$ 1000?"
python -m app.cli status
```

The CLI is useful for testing the agent without the UI and for capturing example conversations.

### 4. Tests and lint

```bash
python -m pytest -q
ruff check app scripts tests
node --check app/web/static/chat.js
```

The test suite uses `FakeLLM` and `FakeEmbeddingClient`; it makes no real OpenAI calls. There are **46 tests** covering ingestion, money, catalog, orders, shipping, store hours, policy retrieval (including English queries), the agent loop, guardrails, and HTTP routes.

### 5. Re-extract the manual (optional)

```bash
python scripts/extract_policy.py
```

The script uses `pdfplumber` and writes `data/policy_sections.json`. The JSON is committed so the runtime does not depend on PDF parsing. The hours and payment tables were checked manually.

## Architecture

```text
Browser
  ├─ Jinja2 + HTMX (chat, filters, operational panel)
  └─ fetch/SSE (token streaming)
        │
FastAPI (app/web/routes.py)
        │
Agent (app/agent/orchestrator.py)
  ├─ Responses API + tool calling
  ├─ typed tools (app/agent/tools.py)
  └─ guardrails (app/agent/guardrails.py)
        │
Domain (app/domain/)
  ├─ catalog, orders, promotions
  ├─ shipping, store hours
  └─ hybrid policy retrieval
        │
SQLite
  ├─ operational tables
  ├─ policy_sections + embedding BLOBs
  ├─ FTS5 (policy_fts, product_fts)
  ├─ sessions, messages
  └─ agent_runs, tool_calls, data_quality_issues
```

The agent core does not depend on FastAPI. The web layer only presents; the domain layer does not know the model. This keeps the agent testable without a server and makes it possible to swap SQLite or the provider without rewriting the logic.

## Technical decisions

### Model and API

I used **`gpt-6-luna`** for its cost/latency profile and because it supports function calling and streaming. The integration uses the **Responses API** (`v1/responses`): the model documentation states that Chat Completions only supports function calling with `reasoning_effort=none`, while the Responses API supports the full tool flow with reasoning.

- `reasoning.effort` comes from `REASONING_EFFORT` in `.env`; the default is `low`.
- `store=False` avoids server-side response storage; conversation state lives in SQLite.
- The loop preserves reasoning items returned by the model, as required for reasoning models with tool calls.
- `parallel_tool_calls=False` keeps traces deterministic.
- The adapter is in `app/llm/openai_responses.py`; another provider can implement the same protocol.

### Interface

FastAPI + Jinja2 + HTMX handles navigation, filters, and forms without a front-end build. Chat streaming uses a small `fetch` + SSE reader in `app/web/static/chat.js`, because HTMX's EventSource is GET-only and the chat needs to POST a message. The rest of the UI remains HTMX.

### Database

SQLite is enough for 65 products, 20 orders, and an 8-page policy manual. It provides transactions, FTS5, indexes, and a single file for the demo with no infrastructure. Money is stored as **integer cents** to avoid floating-point errors. Dates are stored as ISO strings. The database is generated by a script and is not committed.

For the operational panel and conversation history, SQLite is also sufficient. For multi-user/high-concurrency production, the next step would be Postgres; the repository layer isolates the SQL.

### Policy retrieval

The manual is small, so I did not use a vector database. The strategy is hybrid:

1. Offline extraction into 26 sections by real headings (4.1, 6.2, 7.3, and so on).
2. Embeddings of `title + text` with `text-embedding-3-large` (3072 dimensions by default; configurable).
3. Vector search by cosine similarity in Python over vectors stored as BLOBs.
4. FTS5 lexical search for exact terms such as “PIX”, “90 days”, and “mouthpiece”.
5. Rank fusion with Reciprocal Rank Fusion (RRF).
6. FTS5 fallback if there is no key, no embeddings, or no network.

I did not use `sqlite-vec` or FAISS: with ~26 sections, brute force is instant and avoids native dependencies. If the manual grows, the retrieval interface allows the implementation to be replaced.

### English queries against Portuguese data

The source data and policy manual are in Portuguese, but customers write in English. The agent uses two layers:

- **Semantic retrieval:** `text-embedding-3-large` is multilingual, so English questions can match Portuguese policy sections.
- **Lexical expansion:** `app/domain/search_aliases.py` maps English terms to Portuguese catalog and policy terms before FTS5 search. Examples:
  - `acoustic guitar` / `classical guitar` → `violão`
  - `guitar` → `guitarra` / `violão`
  - `bass` → `baixo`
  - `double bass` / `upright bass` → `contrabaixo` (orchestral strings)
  - `drums` → `bateria`
  - `keyboard` / `piano` → `teclado` / `piano`
  - `return` / `refund` → `devolução` / `reembolso`
  - `warranty` → `garantia`
  - `shipping` → `frete`
  - `payment` → `pagamento`
  - `exchange` → `troca`
  - `hours` → `horário`
  - `accessories` / `strings` → `acessórios` / `cordas`

Category filters also accept English aliases such as `Acoustic guitars`, `basses`, and `ukuleles`. Compound terms such as `bass guitar` are resolved before generic terms, and multi-category queries such as `guitars and ukuleles` combine the requested categories.

### Agent tools

I did not use a free-form SQL agent. The model receives typed tools with strict schemas and `additionalProperties: false`:

| Tool | Purpose |
|---|---|
| `search_products` | Search by text, category, price range, and availability |
| `get_product` | Product detail, specs, promotion, PIX, and installments |
| `get_active_promotions` | Promotions with `is_active = 1`, original price, and discount |
| `get_order` | Order by ID plus customer verification |
| `search_policy` | Hybrid search over policy sections |
| `get_store_status` | Local time, open/closed, and next opening |
| `get_shipping_estimate` | Shipping rule by city and order total |

Order verification requires `order_id` and a customer identifier (name, phone, or email). On a mismatch, the tool returns a generic “not found” response without confirming whether the order exists.

### Prompt and guardrails

The system prompt is in `app/agent/prompts.py` and defines persona, scope, mandatory tool use, privacy, tone, and format. It explicitly says: **always answer in English**, regardless of the customer's language or the language of tool results.

Beyond the prompt:

- customer messages are treated as data, not instructions;
- BRL values in the answer are compared with tool results; if a value does not appear in any lookup, the run records a warning;
- tool iterations are limited by `MAX_TOOL_ITERATIONS`;
- tool errors become structured results so the model can recover;
- the trace stores arguments, result, latency, tokens, and estimated cost.

## Data treatment

- **CSV as the available catalog.** The manual mentions 300+ instruments, but the CSV has 65. For the prototype, the CSV is the source of truth; no model outside it is invented. The woodwind, brass, and orchestral-strings categories are empty.
- **Status beats stock.** Product 136 is `discontinued` with stock 13; 96 is `active` with stock 0; 130 is `coming_soon` with stock 2 and appears in orders. Availability is derived from status + stock, never from stock alone.
- **Active promotions.** Only 4 of 25 rows have `is_active = 1`. Duplicate rows for products 93, 96, and 99 are inactive. If more than one promotion is active, the highest discount is used.
- **Order total is authoritative.** Orders 3 and 20 have totals lower than the line-item sum. The system does not “fix” the data; it records the mismatch in `data_quality_issues` and uses `orders.total_brl` in answers.
- **PII.** Phone numbers and emails are masked in lists and traces. The panel has no login and should run on `127.0.0.1`; do not expose it publicly.
- **Money and installments.** Values are converted to cents with `Decimal` and `ROUND_HALF_UP`. The 5% PIX discount does not apply to promotions. The manual has an inconsistency between the table (minimum installment of R$ 100) and section 3.1 (4–6x with a minimum of R$ 80); the implementation follows section 3.1 and documents the choice.
- **Dates.** Orders have a purchase date and an estimated delivery date, but not the actual delivery date. For returns, the agent uses the estimate cautiously or asks the customer.
- **No CEP/address.** Customers have only a city. Shipping in Campo Grande follows the R$ 500/R$ 35 rule; outside the region, the agent explains that the CEP is needed to quote PAC, SEDEX, or Jadlog.
- **No holiday calendar.** Hours cover Monday–Saturday and Sunday; holidays are not modeled, and the tool response says so explicitly.

## Project structure

```text
app/
  main.py                  # FastAPI app and lifespan
  config.py                # .env and Settings
  db.py                    # schema, connection, reset
  cli.py                   # chat/ask/status in the terminal
  agent/
    orchestrator.py        # Responses API loop, streaming, persistence
    prompts.py             # system prompt
    tools.py               # schemas and dispatch
    guardrails.py          # value and message validation
  domain/
    catalog.py             # search, availability, prices
    orders.py              # orders, verification, PII masks
    payments.py            # PIX and installments
    policy.py              # hybrid retrieval
    search_aliases.py      # English ↔ Portuguese search terms
    shipping.py            # shipping rules
    store.py               # store hours
  data/
    ingest.py              # CSV + policies -> SQLite
    quality.py             # anomaly checks
  llm/
    base.py                # protocols and dataclasses
    openai_responses.py    # gpt-6-luna adapter
    embeddings.py          # text-embedding-3-large and fake
    fake.py                # deterministic LLM for tests
  web/
    routes.py              # chat, panel, and SSE routes
    templates/             # Jinja2
    static/                # CSS, HTMX, chat.js
data/
  *.csv                    # operational data (Portuguese)
  políticas_da_loja.pdf    # policy manual (Portuguese)
  policy_sections.json     # extracted, reviewed sections
tests/                     # 46 tests
scripts/
  extract_policy.py        # PDF -> sections
examples/                  # English example conversations
```

## Main endpoints

- `GET /` — chat
- `POST /chat/stream` — chat with SSE (`token`, `tool_call`, `tool_result`, `done`, `error`)
- `POST /chat` — non-streaming fallback
- `GET /sessions/{id}` / `POST /sessions/new` — switch and create sessions
- `GET /health` — database and model status
- `GET /ops` — operational dashboard
- `GET /ops/catalog` and `/ops/catalog/{id}` — catalog
- `GET /ops/orders` and `/ops/orders/{id}` — orders
- `GET /ops/traces` and `/ops/traces/{id}` — runs and tools
- `GET /ops/policy` — sections and hybrid search
- `GET /ops/quality` — data-quality anomalies

## Example conversations

- `examples/01-catalog.md` — acoustic guitars under R$ 1,000
- `examples/02-price-stock.md` — Yamaha C40 price, stock, and PIX
- `examples/03-order.md` — order status with customer verification
- `examples/04-return.md` — right of withdrawal policy
- `examples/05-out-of-scope.md` — accessory request and redirect

## Limitations and next steps

- No authentication. The panel and chat are for a local demo; production would need login, role-based authorization, and rate limiting.
- SQLite is single-writer; for multiple simultaneous agents, I would move to Postgres.
- The manual has no actual delivery date and no CEP; some answers depend on the customer providing those details.
- Promotions have no start/end dates; only the `is_active` flag.
- The catalog is a 65-item sample, not the 300+ mentioned in the manual.
- Conversation state is kept as Responses API items in SQLite and grows with use; with more time, I would add summarization and a context limit.
- The trace shows tools and results, not chain-of-thought.
- There is no automated LLM-as-judge evaluation; the tests cover tools, policies, and flow.
- With more time: Docker, Postgres, CEP integration, holiday calendar, panel editing, reranking, embedding cache, and cost/latency metrics.

## AI assistant disclosure

This project was developed with support from **OpenCode** using the **`deepseek-v4.1-flash`** model. The assistant was used to:

- discuss architecture and trade-offs;
- generate the project scaffold and templates;
- implement ingestion, domain services, tools, the agent loop, SSE, and the panel;
- write and run tests;
- review data and policies;
- write this documentation;
- convert the project's user-facing text, documentation, and examples to English.

Decisions were reviewed and validated with local tests. No API keys, real personal data, or secrets were committed. This disclosure is included as requested in the challenge brief.

## Documented assumptions

- The CSV is the available catalog for the prototype, even though the manual mentions 300+ instruments.
- Section 3.1 of the manual prevails over the installment table when they conflict.
- `orders.total_brl` is the source of truth, even when it differs from the line-item sum.
- For returns, the estimated delivery date is used as a reference when the actual date is unavailable; the agent should confirm with the customer.
- Holidays are not modeled; Sundays and holidays are treated as closed.
- Source product names, descriptions, category names, customer names, and policy text remain in Portuguese; the agent and all user-facing output are in English.
