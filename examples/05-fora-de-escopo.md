# Exemplo 5 — Pedido fora do escopo

**Cliente:** Vocês vendem cordas de violão?

**Assistente:** A Empório da Música trabalha exclusivamente com **instrumentos musicais**. Não comercializamos acessórios como cordas, palhetas, cabos, cases, pedais ou amplificadores.

Se você estiver procurando cordas, vale a pena consultar uma loja de acessórios ou um parceiro da região. Por aqui eu posso te ajudar com violões, ukuleles, guitarras, baixos, baterias, teclados e instrumentos de orquestra que estejam no catálogo.

Quer que eu te mostre alguns violões disponíveis?

**Consulta interna**

```text
search_policy(
  query="escopo acessórios cordas palhetas cabos",
  top_k=2
)
```

O agente redireciona sem inventar parceiros ou produtos que a loja não vende.
