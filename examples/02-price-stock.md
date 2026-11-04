# Example 2 — Live price, stock, and PIX lookup

> English translation of an actual local conversation with the OpenAI-backed agent, recorded when the runtime used Portuguese. The runtime now responds in English.

**Customer:** How much is the Yamaha C40?

**Assistant:** The Yamaha C40 Nylon Natural costs **R$ 599,90**. With PIX, it is **R$ 569,91**. We have 12 in stock.

**Observed lookups:** `search_products` followed by `get_product` for the matching catalog item, Yamaha C40 Nylon Natural (`product_id=81`). The response used the database price and stock and the store's calculated 5% PIX discount.

This is a translation of the observed reply, rather than an assertion that the model will produce identical wording on every run. Prices, promotions, and availability reflect the supplied dataset at the time of the run.
