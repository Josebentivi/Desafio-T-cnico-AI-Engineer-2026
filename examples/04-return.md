# Exemplo 4 — Direito de arrependimento

**Cliente:** Me arrependi da compra online. Posso devolver?

**Assistente:** Pode sim, desde que a solicitação seja feita em até **7 dias corridos após o recebimento** do produto. Para a devolução ser aceita, o instrumento precisa estar na embalagem original, sem sinais de uso e com todos os acessórios e manuais.

O frete de devolução fica por conta da loja nesse caso, e o reembolso é feito na mesma forma de pagamento original em até **10 dias úteis**.

Para eu te orientar direitinho, me passa o número do pedido e a data em que você recebeu o instrumento. Se a compra tiver sido de um item personalizado, de venda final ou de uma boquilha de sopro, a troca não se aplica.

**Consulta interna**

```text
search_policy(
  query="direito de arrependimento devolução compra online",
  top_k=3
)
```

A resposta aplica a seção **4.1** do manual. O agente não inventou um prazo nem prometeu reembolso fora da política.
