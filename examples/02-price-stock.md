# Example 2 — Price, stock, and PIX

**Customer:** How much is the Yamaha C40? Do you have it in stock?

**Assistant:** The **Yamaha C40 Nylon Natural** is **R$ 599,90**, and we have **12 units** in stock.

It is active and has no current promotion. With the **5% PIX discount**, it comes to **R$ 569,91**. We also accept debit card, boleto, and credit card, subject to the minimum installment.

Would you like more details about its specifications or payment options?

**Internal lookup**

```text
get_product(product_id=81)
```

The price and stock came from the database. The PIX value was calculated by the store rule and does not stack with promotions.
