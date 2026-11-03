# AGENTS.md

## Repo purpose
Take-home challenge for Artefact's AI Engineer role: a Python text-message customer-service agent for the fictional **Empório da Música**, a musical instrument store in Campo Grande/MS. The agent must adopt the store persona, answer from the provided data and policies, decide when to query operational data vs. policy, and politely handle out-of-scope messages.

The app is a FastAPI + Jinja2 + HTMX chat with a read-only operational panel, SQLite persistence, OpenAI `gpt-6-luna` via the Responses API, and `text-embedding-3-large` for policy retrieval. The challenge brief is the source of truth for deliverables; the policy PDF is the source of truth for business rules.

## Commands
```powershell
pip install -r requirements-dev.txt
copy .env.example .env            # fill OPENAI_API_KEY
python -m app.data.ingest --reset  # CSV + policy sections + embeddings
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
python -m app.cli chat
python -m app.cli status
python -m pytest -q                # use python -m; bare `pytest` may use another interpreter
ruff check app scripts tests
python scripts/extract_policy.py   # regenerate data/policy_sections.json from the PDF
```

If no API key is available, use `python -m app.data.ingest --reset --skip-embeddings`; policy retrieval falls back to FTS5. The app auto-seeds CSVs without embeddings if the database is empty.

## Deliverables and workflow constraints
- Python is the only mandatory technical constraint.
- Final deliverable is a public GitHub repo with a real, incremental commit history; never squash everything into one commit or force-push.
- `README.md` must cover setup/run commands, model/provider, agent/retrieval/prompt decisions, known limitations, and disclosure of any AI coding assistant used.
- Include 3–5 example conversations (`.md` or `.txt`); at least one must show live data lookup or policy application.
- The brief forbids changes after the delivery deadline; freeze the repo then.
- The project root is a git repo with incremental commits. A nested `Desafio Técnico AI Engineer 2026/` directory contains its own `.git` with only `.gitattributes`; it is ignored by the root repo. Do not delete or absorb it without confirmation.
- Do not commit `.env`, `data/app.db`, or generated caches.

## Architecture
- `app/agent/` — Responses API loop, system prompt, typed tools, guardrails. Keep it independent of FastAPI.
- `app/domain/` — catalog, orders, promotions, payments, shipping, store hours, policy retrieval. No LLM or web imports.
- `app/data/` — CSV ingestion, policy sections, data-quality checks.
- `app/llm/` — `LLMClient`/`EmbeddingClient` protocols plus OpenAI and fake adapters.
- `app/web/` — FastAPI routes, Jinja2 templates, HTMX, SSE chat JS.
- `tests/` — pytest with `FakeLLM` and `FakeEmbeddingClient`; no real API calls.

## Model and retrieval constraints
- Use the **Responses API** (`client.responses.create`), not Chat Completions: gpt-6-luna only supports function calling in Chat Completions with `reasoning_effort=none`.
- Preserve all `response.output` items (including reasoning items) when continuing after tool calls; the state is stored in `sessions.state_json`.
- `reasoning.effort` comes from `.env` (`REASONING_EFFORT`, default `low`). `MAX_OUTPUT_TOKENS` must leave room for reasoning tokens; the default is 4000.
- Use `store=False`; stateless Responses include encrypted reasoning content by default. Do not enable OpenAI `web_search`/`file_search` for store facts.
- Policy retrieval is hybrid: section embeddings + FTS5, fused with RRF. Do not replace it with a vector DB without a measured need.
- Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` requires re-running ingestion; embeddings are skipped only when content hash and model label match.

## Data facts and traps (`data/`)
- Files are `desafio_tecnico_ai_eng - <name>.csv` (spaces around the hyphen; quote paths). Comma-separated, UTF-8 **without BOM**. On Windows PowerShell 5.1, `Get-Content` defaults to ANSI and garbles accents; use `-Encoding UTF8` or Python `encoding="utf-8"`.
- Use Python's `csv` module: descriptions contain commas/accents and `products.specs` is an embedded JSON object with escaped quotes.
- Row counts: products 65, categories 9, customers 50, orders 20, order_items 22, promotions 25; policy sections 26.
- Joins: `order_items.order_id -> orders.order_id`, `orders.customer_id -> customers.customer_id`, `products.category_id -> categories.category_id`. All current foreign keys resolve.
- `products.status`: `active` (62), `discontinued` (2), `coming_soon` (1). `orders.status`: `delivered`, `confirmed`, `pending`, `cancelled`, `shipped`.
- Status beats stock: product 136 is `discontinued` but has stock 13; product 96 is `active` with stock 0; product 130 is `coming_soon` with stock 2 and appears in orders 3 and 14. Never confirm availability from `stock_quantity` alone.
- `promotions.is_active`: only 4 of 25 rows are active; filter on it. Products 93/96/99 have duplicate promotion rows, but all are inactive.
- `orders.total_brl` is authoritative. Recomputing from `order_items` × `products.price_brl` does not match orders 3 and 20 (totals are lower than the line-item sum); do not "correct" the data. Ingestion records these as quality issues.
- Categories 6, 7, 8 (sopro madeiras/metais, cordas orquestrais) have zero products. The policy claims 300+ instruments, but this CSV has 65; assume the CSV is the available catalog for this prototype and never invent unlisted models.
- `price_brl` is a decimal-point float (e.g. `599.9`); store cents as integers with `Decimal`, format BRL only at presentation.
- `customers` has `city` but no address. `orders.tracking_code` follows `BR` + 9 alphanumerics + `BR`.
- Rows contain PII. The dataset has no authentication; order lookups require `order_id` plus a matching customer field, and lists/traces mask phone and email. Do not dump the customers table.

## Business rules the agent must honor
Source: `data/políticas_da_loja.pdf` (v2.1, June 2025), extracted to `data/policy_sections.json`. Retrieve from the PDF/JSON; if any rule is hardcoded, keep it in one place.

- Scope: instruments only. The store does **not** sell accessories (strings, picks, cables, cases, pedals, amps); redirect politely and suggest partner stores.
- Never state price, stock, or delivery time without a data lookup; the manual explicitly forbids guessing.
- Returns: 7 calendar days after receipt for online withdrawal (store pays return shipping; refund in 10 business days), 30 days after purchase for defect exchange, 90-day legal warranty, 7 days for preference exchange (subject to availability). Exclusions: customized/set-up instruments, final-sale items, wind mouthpieces.
- Payment: PIX 5% off; debit; credit up to 12x interest-free; boleto. Promotions are not cumulative and the PIX discount does not stack on promotional prices; show original price + discount % for active promos. The installment table (min R$100) conflicts with section 3.1 (4–6x min R$80); prefer 3.1 and document the assumption.
- Shipping: free above R$500 in greater Campo Grande, otherwise R$35 (1–3 business days); outside the region via PAC/SEDEX/Jadlog. There is no CEP/address in the data, so outside-region freight requires a quote.
- Hours: Mon–Fri 09:00–18:00, Sat 09:00–13:00, Sun/holidays closed. Out-of-hours replies must state when the team returns. Holidays are not modeled.
- Tone: informal but professional, "like a friend who knows music", not robotic. Complaints: empathize, log, forward, 24-business-hour return.
- Store address/contact: in the policy PDF; retrieve rather than invent.
- `orders` has no actual delivery date; use `estimated_delivery` cautiously or ask the customer.

## Conventions
- The application uses Brazilian Portuguese (pt-BR): agent replies, UI copy, CLI messages, validation, and runtime errors. README and explanatory documentation, including the documented example conversations, remain in English. English examples are reviewer-facing translations of the Portuguese runtime. Keep product names, customer names, technical identifiers, and policy section numbers as they appear in the source data. The source CSVs and policy manual remain Portuguese.
- The brief allows ignoring tables you do not need; use the minimum data required and justify it.
- Keep policy retrieval and domain rules testable without network access.
- When adding endpoints or tools, update `README.md` and the tests.
