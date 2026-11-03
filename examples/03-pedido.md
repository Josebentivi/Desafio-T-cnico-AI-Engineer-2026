# Exemplo 3 — Status de pedido com verificação

**Cliente:** Qual o status do pedido 1? Meu nome é Pedro Henrique Oliveira.

**Assistente:** Encontrei o **pedido 1**, do Pedro Henrique Oliveira, e ele consta como **entregue**.

- **Item:** Martin D-28 Dreadnought Natural (1 unidade)
- **Total:** R$ 11.499,00
- **Pagamento:** PIX
- **Rastreio:** BRAB1234567BR

A entrega estimada já passou e o pedido está marcado como entregue. Se precisar de algo sobre a nota, a garantia ou uma troca, me diga.

**Consulta interna**

```text
get_order(
  order_id=1,
  customer_verifier="Pedro Henrique Oliveira"
)
```

O agente exigiu o número do pedido e um dado do cliente antes de revelar o status. Com um nome que não confere, a ferramenta retorna apenas “não encontrado ou dados não conferem”.
