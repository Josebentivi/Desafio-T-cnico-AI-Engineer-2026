# Exemplo 2 — Preço, estoque e PIX

**Cliente:** Quanto custa o Yamaha C40? Tem em estoque?

**Assistente:** O **Yamaha C40 Nylon Natural** está **R$ 599,90** e temos **12 unidades** em estoque.

Ele está ativo, sem promoção vigente. No **PIX**, com 5% de desconto, fica **R$ 569,91**. Também aceitamos débito, boleto e crédito em até 12x sem juros, respeitando a parcela mínima.

Quer que eu te conte mais sobre as especificações ou sobre as formas de pagamento?

**Consulta interna**

```text
get_product(product_id=81)
```

O preço e o estoque vieram do banco; o valor do PIX foi calculado pela regra da loja, sem acumular com promoção.
