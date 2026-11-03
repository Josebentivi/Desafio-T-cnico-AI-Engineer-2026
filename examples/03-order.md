# Example 3 — Order status with verification

> English reviewer-facing translation. The application replies in Brazilian Portuguese (pt-BR).

**Customer:** What is the status of order 1? My name is Pedro Henrique Oliveira.

**Assistant:** I found **order 1** for Pedro Henrique Oliveira, and it is marked as **delivered**.

- **Item:** Martin D-28 Dreadnought Natural (1 unit)
- **Total:** R$ 11.499,00
- **Payment:** PIX
- **Tracking:** BRAB1234567BR

The estimated delivery date has passed and the order is marked as delivered. If you need anything about the invoice, warranty, or an exchange, just let me know.

**Internal lookup**

```text
get_order(
  order_id=1,
  customer_verifier="Pedro Henrique Oliveira"
)
```

The agent required both the order number and a customer identifier before revealing the status. With a name that does not match, the tool returns only “not found or details do not match”.
