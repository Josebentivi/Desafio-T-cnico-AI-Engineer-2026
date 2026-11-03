# Empório da Música — agente de atendimento

Agente de mensagens de texto para a fictícia **Empório da Música**, loja de instrumentos musicais de Campo Grande/MS. O projeto foi construído para o desafio técnico de AI Engineer da Artefact.

O agente conversa em português do Brasil, consulta o catálogo e os pedidos no SQLite, recupera regras do manual de políticas e só afirma preço, estoque, prazo ou status depois de consultar uma ferramenta. A interface tem um chat com streaming e um painel operacional somente leitura com catálogo, pedidos, políticas, qualidade dos dados e traces das execuções.

## Stack

- Python 3.11+
- FastAPI + Jinja2 + HTMX
- SQLite + FTS5
- OpenAI **`gpt-6-luna`** via **Responses API**
- OpenAI **`text-embedding-3-large`** para busca semântica das políticas
- `numpy` para similaridade de cosseno
- `pdfplumber` apenas na extração offline do manual

## Como rodar

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env
# edite .env e preencha OPENAI_API_KEY
```

O arquivo `.env` concentra o modelo, o provedor, o esforço de reasoning, as dimensões dos embeddings, o caminho do banco e as configurações do servidor. O `OPENAI_API_KEY` nunca deve ser commitado.

### 1. Ingestão

```bash
python -m app.data.ingest --reset
```

Esse comando:

- cria o schema do SQLite;
- lê os seis CSVs de `data/`;
- converte dinheiro para centavos e valida datas, status e chaves estrangeiras;
- extrai as seções do manual de políticas de `data/policy_sections.json`;
- gera os embeddings das seções com `text-embedding-3-large` (se houver chave);
- monta os índices FTS5;
- registra anomalias de dados em `data_quality_issues`.

Sem chave da OpenAI, ou para economizar chamadas:

```bash
python -m app.data.ingest --reset --skip-embeddings
```

Nesse modo a busca de políticas usa apenas FTS5; o chat continua funcionando, mas sem busca semântica.

### 2. Servidor

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Chat: http://127.0.0.1:8000/
- Painel: http://127.0.0.1:8000/ops
- Saúde: http://127.0.0.1:8000/health

Na primeira inicialização, se o banco estiver vazio, o app faz um seed automático dos CSVs sem embeddings. Para a experiência completa, rode a ingestão antes.

### 3. CLI

```bash
python -m app.cli chat
python -m app.cli ask "Quais violões vocês têm até R$ 1000?"
python -m app.cli status
```

O CLI é útil para testar o agente sem a interface e para capturar conversas de exemplo.

### 4. Testes e lint

```bash
python -m pytest -q
ruff check app scripts tests
```

Os testes usam `FakeLLM` e `FakeEmbeddingClient`; não fazem chamadas reais à OpenAI. São 36 testes cobrindo ingestão, dinheiro, catálogo, pedidos, frete, horário, políticas, loop do agente, guardrails e rotas HTTP.

### 5. Reextrair o manual (opcional)

```bash
python scripts/extract_policy.py
```

O script usa `pdfplumber` e gera `data/policy_sections.json`. O JSON é commitado para o runtime não depender de parsing de PDF. As tabelas de horário e pagamento foram conferidas manualmente.

## Arquitetura

```text
Navegador
  ├─ Jinja2 + HTMX (chat, filtros, painel)
  └─ fetch/SSE (streaming de tokens)
        │
FastAPI (app/web/routes.py)
        │
Agent (app/agent/orchestrator.py)
  ├─ Responses API + tool calling
  ├─ tools tipadas (app/agent/tools.py)
  └─ guardrails (app/agent/guardrails.py)
        │
Domínio (app/domain/)
  ├─ catálogo, pedidos, promoções
  ├─ frete, horário da loja
  └─ busca híbrida de políticas
        │
SQLite
  ├─ tabelas operacionais
  ├─ policy_sections + embeddings BLOB
  ├─ FTS5 (policy_fts, product_fts)
  ├─ sessões, mensagens
  └─ agent_runs, tool_calls, data_quality_issues
```

O núcleo do agente não depende de FastAPI. A camada web só apresenta; o domínio não conhece o modelo. Isso permite testar o agente sem servidor e trocar SQLite ou provedor sem reescrever a lógica.

## Decisões técnicas

### Modelo e API

Usei **`gpt-6-luna`** pela relação custo/latência e porque o modelo suporta function calling e streaming. A integração usa a **Responses API** (`v1/responses`): a documentação do modelo indica que o Chat Completions só suporta function calling com `reasoning_effort=none`, enquanto a Responses API suporta o fluxo completo de ferramentas com reasoning.

- `reasoning.effort` vem de `REASONING_EFFORT` no `.env`; o padrão é `low`.
- `store=False` evita retenção do lado da OpenAI; o estado da conversa fica no SQLite.
- O loop preserva os itens de reasoning retornados pelo modelo, como a documentação exige para modelos de reasoning com tool calls.
- `parallel_tool_calls=False` deixa o trace determinístico.
- O adapter está em `app/llm/openai_responses.py`; trocar de provedor significa implementar o mesmo protocolo.

### Interface

FastAPI + Jinja2 + HTMX cobre navegação, filtros e formulários sem build de front-end. O streaming do chat usa um pequeno `fetch` com leitura de SSE em `app/web/static/chat.js`, porque o EventSource do HTMX é GET e o chat precisa enviar uma mensagem por POST. O restante da UI continua em HTMX.

### Banco

SQLite é suficiente para 65 produtos, 20 pedidos e 8 páginas de política. Ele dá transações, FTS5, índices e um arquivo único para o demo, sem infraestrutura. O dinheiro é armazenado em **centavos inteiros** para evitar erros de ponto flutuante. Datas ficam em ISO. O banco é gerado por script e não é commitado.

Para o painel operacional e o histórico de conversa, SQLite também resolve. Para multiusuário/concorrência alta, o próximo passo seria Postgres; a camada de repositórios isola o SQL.

### Busca das políticas

O manual é pequeno, então não usei vector database. A estratégia é híbrida:

1. Extração offline em 26 seções por título real (4.1, 6.2, 7.3 etc.).
2. Embeddings de `title + text` com `text-embedding-3-large` (3072 dimensões por padrão; configurável).
3. Busca vetorial por similaridade de cosseno em Python, sobre os vetores armazenados como BLOB.
4. Busca lexical FTS5 para termos exatos como “PIX”, “90 dias”, “boquilha”.
5. Fusão dos rankings por Reciprocal Rank Fusion (RRF).
6. Fallback para FTS5 se não houver chave, embeddings ou rede.

Não usei `sqlite-vec` nem FAISS: com ~26 seções, força bruta é instantânea e reduz dependências nativas. Se o manual crescer, a interface de retrieval permite trocar a implementação.

### Ferramentas do agente

Não usei “agente SQL” livre. O modelo recebe ferramentas tipadas, com schemas estritos e `additionalProperties: false`:

| Ferramenta | Uso |
|---|---|
| `search_products` | Busca por texto, categoria, faixa de preço e disponibilidade |
| `get_product` | Detalhe de produto, specs, promoção, PIX e parcelamento |
| `get_active_promotions` | Promoções com `is_active = 1`, preço original e desconto |
| `get_order` | Pedido por ID + verificação do cliente |
| `search_policy` | Busca híbrida nas seções do manual |
| `get_store_status` | Horário local, aberto/fechado e próximo atendimento |
| `get_shipping_estimate` | Regra de frete por cidade e total |

A verificação de pedido exige `order_id` e um dado do cliente (nome, telefone ou e-mail). Em caso de divergência, a ferramenta retorna um “não encontrado” genérico, sem confirmar se o pedido existe.

### Prompt e guardrails

O system prompt fica em `app/agent/prompts.py` e define persona, escopo, uso obrigatório de ferramentas, privacidade, tom e formato. Além do prompt:

- mensagens do usuário são tratadas como dados, não instruções;
- valores em reais na resposta são comparados com os resultados das ferramentas; se um valor não aparecer em nenhuma consulta, a execução registra um aviso;
- o número de iterações de ferramentas é limitado por `MAX_TOOL_ITERATIONS`;
- erros de ferramenta viram resultado estruturado para o modelo se recuperar;
- o trace guarda argumentos, resultado, latência, tokens e custo estimado.

## Tratamento dos dados

- **CSV como catálogo disponível.** O manual fala em 300+ instrumentos, mas o CSV tem 65. Para o protótipo, o CSV é a fonte de verdade; nenhum modelo fora dele é inventado. As categorias de sopro madeiras, sopro metais e cordas orquestrais estão vazias.
- **Status vence estoque.** Produto 136 é `discontinued` com estoque 13; 96 é `active` com estoque 0; 130 é `coming_soon` com estoque 2 e aparece em pedidos. A disponibilidade é derivada de status + estoque, nunca só do estoque.
- **Promoções ativas.** Só 4 das 25 linhas têm `is_active = 1`. As duplicatas dos produtos 93, 96 e 99 estão inativas. A promoção ativa é escolhida pelo maior desconto se houver mais de uma.
- **Total do pedido é autoritativo.** Os pedidos 3 e 20 têm total menor que a soma dos itens. O sistema não “corrige” os dados; registra a divergência em `data_quality_issues` e usa `orders.total_brl` nas respostas.
- **PII.** Telefones e e-mails são mascarados nas listas e nos traces. O painel não tem login e deve rodar em `127.0.0.1`; não exponha publicamente.
- **Dinheiro e parcelamento.** Valores são convertidos para centavos com `Decimal` e arredondamento `ROUND_HALF_UP`. O PIX de 5% não incide sobre promoção. O manual tem uma inconsistência entre a tabela (parcela mínima de R$ 100) e a seção 3.1 (4–6x com mínima de R$ 80); a implementação segue a seção 3.1 e documenta a escolha.
- **Datas.** O pedido tem data de compra e entrega estimada, mas não a data real de recebimento. Para devolução, o agente usa a estimativa com cautela ou pergunta ao cliente.
- **Sem CEP/endereço.** O cliente tem apenas cidade. O frete em Campo Grande segue a regra de R$ 500/R$ 35; fora da região, o agente explica que precisa do CEP para cotar PAC, SEDEX ou Jadlog.
- **Sem calendário de feriados.** O horário cobre segunda a sábado e domingo; feriados não estão modelados e isso está explícito na resposta da ferramenta.

## Estrutura

```text
app/
  main.py                  # criação do FastAPI e lifespan
  config.py                # .env e Settings
  db.py                    # schema, conexão, reset
  cli.py                   # chat/ask/status no terminal
  agent/
    orchestrator.py        # loop Responses API, streaming e persistência
    prompts.py             # system prompt
    tools.py               # schemas e dispatch
    guardrails.py          # validação de valores e tamanho de mensagem
  domain/
    catalog.py             # busca, disponibilidade, preços
    orders.py              # pedido, verificação, máscaras de PII
    payments.py            # PIX e parcelamento
    policy.py              # busca híbrida
    shipping.py            # regra de frete
    store.py               # horário da loja
  data/
    ingest.py              # CSV + políticas -> SQLite
    quality.py             # anomalias
  llm/
    base.py                # protocolos e dataclasses
    openai_responses.py    # adapter gpt-6-luna
    embeddings.py          # text-embedding-3-large e fake
    fake.py                # LLM determinística para testes
  web/
    routes.py              # rotas do chat, painel e SSE
    templates/             # Jinja2
    static/                # CSS, HTMX e chat.js
data/
  *.csv                    # dados operacionais
  políticas_da_loja.pdf    # manual
  policy_sections.json     # seções extraídas e revisadas
tests/                     # 36 testes
scripts/
  extract_policy.py        # PDF -> seções
examples/                  # conversas de exemplo
```

## Endpoints principais

- `GET /` — chat
- `POST /chat/stream` — chat com SSE (`token`, `tool_call`, `tool_result`, `done`, `error`)
- `POST /chat` — fallback sem streaming
- `GET /sessions/{id}` / `POST /sessions/new` — troca e criação de sessão
- `GET /health` — estado do banco e do modelo
- `GET /ops` — painel
- `GET /ops/catalog` e `/ops/catalog/{id}` — catálogo
- `GET /ops/orders` e `/ops/orders/{id}` — pedidos
- `GET /ops/traces` e `/ops/traces/{id}` — execuções e ferramentas
- `GET /ops/policy` — seções e busca híbrida
- `GET /ops/quality` — anomalias

## Exemplos de conversa

- `examples/01-catalogo.md` — busca de violões até R$ 1.000
- `examples/02-preco-estoque.md` — preço, estoque e PIX do Yamaha C40
- `examples/03-pedido.md` — status do pedido com verificação do cliente
- `examples/04-devolucao.md` — aplicação da política de arrependimento
- `examples/05-fora-de-escopo.md` — pedido de acessório e redirecionamento

## Limitações e próximos passos

- Sem autenticação. O painel e o chat são para demo local; em produção seria necessário login, autorização por papel e rate limiting.
- SQLite é single-writer; para múltiplos atendentes simultâneos, migraria para Postgres.
- O manual não tem data real de recebimento nem CEP; algumas respostas dependem de o cliente informar esses dados.
- Promoções não têm data de início/fim; só o flag `is_active`.
- O catálogo é uma amostra de 65 itens, não os 300+ citados no manual.
- O estado da conversa é mantido como itens da Responses API no SQLite e cresce com o uso; com mais tempo, adicionaria sumarização e limite de contexto.
- O trace mostra ferramentas e resultados, não chain-of-thought.
- Não há avaliação automatizada de qualidade das respostas com LLM-as-judge; os testes cobrem ferramentas, políticas e fluxo.
- Com mais tempo: Docker, Postgres, integração de CEP, calendário de feriados, edição no painel, reranker, cache de embeddings e métricas de custo/latência.

## Uso de assistentes de código

Este projeto foi desenvolvido com apoio do **OpenCode** usando o modelo **`deepseek-v4.1-flash`**. O assistente foi usado para:

- discutir a arquitetura e os trade-offs;
- gerar o scaffold do projeto e os templates;
- implementar ingestão, domínio, ferramentas, loop do agente, SSE e painel;
- escrever e rodar os testes;
- revisar dados e políticas;
- redigir esta documentação.

As decisões foram revisadas e validadas com testes locais. Nenhuma chave de API, dado pessoal real ou segredo foi commitado. O uso de IA está declarado aqui conforme pedido no enunciado.

## Premissas documentadas

- O CSV é o catálogo disponível para o protótipo, mesmo que o manual cite 300+ instrumentos.
- A seção 3.1 do manual prevalece sobre a tabela de parcelamento quando há conflito.
- `orders.total_brl` é a fonte de verdade, mesmo quando diverge da soma dos itens.
- Para devolução, a data estimada de entrega é usada como referência quando a data real não está disponível; o agente deve confirmar com o cliente.
- Feriados não estão modelados; domingos e feriados seguem fechados.
