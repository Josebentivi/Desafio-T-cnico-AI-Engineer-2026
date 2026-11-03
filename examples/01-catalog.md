# Example 1 — Catalog search

> English reviewer-facing translation. The application replies in Brazilian Portuguese (pt-BR).

**Customer:** Which acoustic guitars do you have under R$ 1,000?

**Assistant:** Here are a few available options:

- **Tagima Memphis AC-39 Nylon Natural** — R$ 429,90 (15 in stock)
- **Rozini RC-104 Nylon Estudante** — R$ 459,90 (10 in stock)
- **Yamaha C40 Nylon Natural** — R$ 599,90 (12 in stock)
- **Yamaha C70 Nylon Natural** — R$ 849,00 (8 in stock)
- **Tagima Woodstock Dreadnought Natural** — R$ 899,00 (11 in stock)

All of them are active and available. Would you like to compare body style, string type, or finish?

**Internal lookup**

```text
search_products(
  query="acoustic guitar",
  max_price_brl=1000,
  only_available=true,
  limit=10
)
```

The agent only listed products present in the CSV with `status = active` and positive stock. The English query was expanded to the Portuguese catalog terms (`violão`) before the FTS5 search.
