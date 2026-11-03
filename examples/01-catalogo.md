# Exemplo 1 — Busca no catálogo

**Cliente:** Quais violões vocês têm até R$ 1.000?

**Assistente:** Separei algumas opções de violão que cabem no seu orçamento:

- **Yamaha C40 Nylon Natural** — R$ 599,90 (12 em estoque)
- **Yamaha C70 Nylon Natural** — R$ 849,00 (8 em estoque)
- **Tagima Woodstock Dreadnought Natural** — R$ 899,00 (11 em estoque)
- **Rozini RC-104 Nylon Estudante** — R$ 459,90 (10 em estoque)

Todas estão ativas e disponíveis. Se quiser, posso comparar o tamanho, o tipo de corda ou o acabamento de alguma delas.

**Consulta interna**

```text
search_products(
  query="violão",
  max_price_brl=1000,
  only_available=true,
  limit=10
)
```

O agente só listou produtos presentes no CSV e com `status = active` e estoque positivo.
