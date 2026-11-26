# Especificação do Projeto — Dashboard Financeiro Local

## 1. Objetivo

Uma aplicação financeira **100% local e sem overengineering** para consolidar extratos CSV de múltiplos bancos e cartões em um banco SQLite, permitindo:

- Importar CSVs de bancos diferentes com perfis reutilizáveis e proteção contra duplicatas.
- Renomear lançamentos preservando o texto/data/valor originais para **retro-validação** com o extrato bancário e **matching automático** de entradas futuras.
- Visualizar finanças de forma **consolidada** (todos os bancos) ou **segmentada** (por banco ou conta específica).
- Planejar o mês enxergando claramente **quanto da renda já está comprometido** (gastos realizados + contas fixas pendentes + parcelas futuras de cartão).
- Acompanhar **orçamentos mensais por categoria** e **saldos das contas** ao longo do tempo.

## 2. Arquitetura & Stack

- **Servidor único**: FastAPI + Jinja2 HTML + HTMX + Chart.js (ambos vendorizados localmente em `app/static/vendor/` para funcionamento 100% offline).
- **Persistência**: SQLite local em `data/finances.db` (WAL mode + `PRAGMA foreign_keys = ON`).
- **Locale**: Interface inteira em `pt-BR`, valores monetários em BRL (`R$ 1.234,56`) armazenados como inteiros em **centavos** (`amount_cents`) para eliminar erros de ponto flutuante.

## 3. Modelo de Dados (SQLite)

### `banks`
- `id`, `name` (ex.: Itaú, Nubank, Inter), `color`, `created_at`

### `accounts`
- `id`, `bank_id` (FK), `name` (ex.: Conta Corrente, Cartão Black), `account_type` (`checking` | `credit_card` | `savings`)
- `initial_balance_cents` (inteiro, padrão `0`), `initial_balance_date` (`YYYY-MM-DD`, opcional) — checkpoint de saldo para contas correntes/poupança. O usuário informa o **saldo atual** (data de referência padrão = hoje); o saldo é o do fim do dia `initial_balance_date`.

### `import_profiles`
- `id`, `name`, `account_id` (FK opcional para vincular direto à conta), `delimiter` (`,` ou `;` ou `\t`), `has_header` (bool), `encoding` (`utf-8-sig` / `latin-1`), `date_column`, `description_column`, `amount_column`, `date_format` (`%Y-%m-%d`, `%d/%m/%Y`, etc.), `decimal_separator` (`.` ou `,`), `expense_sign` (`negative` para extratos de conta onde gasto é `-50,00`; `positive` para faturas de cartão onde compra é `50.00`).
- Presets iniciais prontos para uso (ex.: Fatura CSV padrão `data,lançamento,valor` e Extrato Conta `;` `DD/MM/YYYY`).

### `import_batches`
- `id`, `account_id` (FK), `profile_id` (FK opcional), `filename`, `competence_month` (`YYYY-MM`, opcional), `row_count`, `imported_at`.
- Permite **desfazer uma importação inteira em 1 clique** (`ON DELETE CASCADE` em `transactions`).

### `categories`
- `id`, `name`, `color`, `monthly_budget_cents` (opcional — teto mensal para barra de progresso no dashboard).

### `rules`
- `id`, `pattern`, `match_type` (`exact` | `contains`), `normalized_pattern`, `target_display_name`, `target_category_id` (FK opcional), `target_kind` (`expense` | `income` | `transfer` | NULL), `priority`, `created_at`.
- Normalização automática: lowercase, colapso de espaços e remoção de sufixo de parcela (`02/06`, `2/6`, `PARC 02/06`).

### `transactions`
- Identidade & Origem: `id`, `account_id` (FK), `import_batch_id` (FK)
- **Campos imutáveis para retro-validação**: `raw_date` (`YYYY-MM-DD`), `raw_description`, `raw_amount_cents` (sinal normalizado de fluxo de caixa na conta: negativo = saída/despesa, positivo = entrada/receita), `raw_csv_row` (JSON da linha original), `dedup_hash`.
- **Campos de classificação**: `competence_month` (`YYYY-MM`), `display_name`, `category_id` (FK opcional), `kind` (`expense` | `income` | `transfer`), `notes`.
- **Parcelas (registradas explicitamente)**: `installment_current` (int opcional), `installment_total` (int opcional), `installment_group_key` (texto normalizado para projeção sem duplicar parcelas já importadas). Não são mais inferidas de textos `DD/MM` nos extratos importados; ficam vazias na importação até existir uma fonte explícita (futura importação de operações de cartão).

### `bill_payment_links`
- `id`, `payment_transaction_id` (FK única para `transactions.id` com `ON DELETE CASCADE`), `card_account_id` (FK para `accounts.id`), `competence_month` (`YYYY-MM`), `created_at`.
- Conecta um ou mais pagamentos feitos na conta corrente/poupança a uma fatura `(card_account_id, competence_month)` para conferência de valores e controle automático de dupla contagem.

### `recurring_items`
- `id`, `name`, `kind` (`income` | `expense`), `expected_amount_cents`, `day_of_month` (1–31), `account_id` (FK opcional), `category_id` (FK opcional), `match_keyword` (para reconciliação automática com lançamentos importados), `active` (bool), `start_month` (`YYYY-MM`, opcional), `end_month` (`YYYY-MM`, opcional).

### `recurring_matches`
- `id`, `recurring_item_id` (FK), `competence_month` (`YYYY-MM`), `transaction_id` (FK opcional), `status` (`paid` | `skipped`), `actual_amount_cents` (opcional).
- Garante reconciliação entre o previsto e o realizado: uma conta recorrente marcada como paga (automaticamente ou em 1 clique) deixa de somar em "Comprometido Pendente", evitando dupla contagem.

## 4. Regras de Negócio Principais

1. **Deduplicação inteligente**: para cada arquivo importado, conta ocorrências idênticas de `(account_id, raw_date, raw_amount_cents, raw_description)` no mesmo dia e gera um hash com o índice da ocorrência (`#1`, `#2`, ...). Reimportar o mesmo mês ignora as já existentes sem descartar duas compras reais idênticas no mesmo dia. O preview permite inspecionar e forçar importação de qualquer linha marcada como duplicata.
2. **Transferências / Pagamento de Fatura (`transfer`) e Detalhamento de Fatura**:
   - Excluídos de Receitas e Despesas na visão consolidada (e nos orçamentos por categoria).
   - **Incluídos** no cálculo do saldo real de cada conta corrente/poupança (checkpoint bidirecional por `raw_date`: para o fim de mês `M >= initial_balance_date`, `saldo = initial_balance + soma(raw_amount_cents)` com `initial_balance_date < raw_date <= M`; para `M < initial_balance_date`, retroage invertendo os sinais: `saldo = initial_balance - soma(raw_amount_cents)` com `M < raw_date <= initial_balance_date`), porque pagar a fatura de fato reduz o dinheiro disponível na conta corrente.
   - **Detalhar / Vincular fatura**: em `/lancamentos`, saídas de conta corrente/poupança marcadas como `Transferência / Fatura` oferecem a ação "Detalhar fatura" para vincular a uma fatura já importada no cartão ou ir para `/importar` pré-preenchido com conferência ao vivo (`Bateu ✓` ou `Diferença de R$ ...`). Desvincular ou desfazer a última importação daquela fatura reverte o pagamento para `expense`.
3. **Competência vs Data Original**:
   - Conta corrente/poupança: `competence_month = YYYY-MM(raw_date)`.
   - Cartão de crédito: escolhido uma vez no upload da fatura (sugerido automaticamente pelo mês mais recente do CSV), mantendo `raw_date` intacto para auditoria.
4. **Projeção de Parcelas**:
   - Apenas lançamentos de **cartão de crédito** com parcelas registradas explicitamente (`installment_current < installment_total`) geram projeções virtuais (ex.: `02/06` em `2026-11` → `03/06` em `2026-12`, ..., `06/06` em `2027-03`) no planejamento dos meses futuros — suprimidas se a parcela correspondente já tiver sido importada naquele mês. Nenhuma parcela é inferida de `DD/MM` no texto da descrição.
5. **Resumo de Comprometimento Mensal**:
   - **Renda Esperada**: `max(renda_realizada, renda_recorrente_esperada)` ou soma de *Receita Realizada + Receitas Previstas Pendentes*.
   - **Já Gasto (Realizado)**: soma de despesas (`kind = 'expense'`) no mês de competência.
   - **Ainda Comprometido (Previsto Pendente)**: contas recorrentes ainda não pagas no mês + parcelas projetadas de cartão ainda não faturadas no mês.
   - **Total Comprometido**: `Já Gasto + Ainda Comprometido`.
   - **Disponível para Planejar**: `Renda Esperada - Total Comprometido`.

## 5. Telas da Aplicação

1. **Visão Geral (`/`)**: seletor de mês + filtro Global / Banco / Conta; cards de KPI (Receita, Despesa, Saldo do Mês, Comprometido vs Disponível); barra visual de comprometimento mensal; saldos das contas (com evolução); barras de orçamento por categoria; gráfico de despesas por categoria (Chart.js); últimos lançamentos.
2. **Lançamentos (`/lancamentos`)**: filtros por mês, banco, conta, categoria, tipo e busca (no nome limpo e no nome original do banco); edição inline via HTMX para renomear, categorizar, trocar tipo (`Despesa`/`Receita`/`Transferência`), com checkbox "Salvar como regra" (Exato/Contém) e "Aplicar aos lançamentos antigos"; exibição clara do texto original do banco para retro-validação.
3. **Importar CSV (`/importar`)**: seleção de conta, mês da fatura (quando cartão), perfil salvo ou mapeamento visual com preview das primeiras linhas; pré-visualização mostrando linhas novas, regras aplicadas, parcelas detectadas e duplicatas ignoradas (com override); histórico de importações com botão "Desfazer".
4. **Planejamento (`/planejamento`)**: visão detalhada do comprometimento do mês (Receitas previstas, Contas fixas com status Pago/Pendente e vínculo em 1 clique, Parcelas projetadas de cartão) + tabela/gráfico de projeção dos próximos 6 meses.
5. **Configurações (`/configuracoes`)**: CRUD simples de Bancos, Contas (com checkpoint de saldo), Categorias (com orçamento mensal), Regras de Renomeação (com botão "Reaplicar todas as regras") e Perfis de Importação.

## 6. Roadmap Incremental

- [x] **Etapa 1**: Documentação da especificação (`docs/SPEC.md`, `AGENTS.md`) e bootstrap do projeto (`uv` + `pyproject.toml`).
- [x] **Etapa 2**: Esquema SQLite, seed inicial de categorias/presets e serviços de domínio (saldos, regras, projeção de parcelas, planejamento).
- [x] **Etapa 3**: Motor de importação CSV com perfis configuráveis, preview, deduplicação inteligente e undo de lote.
- [x] **Etapa 4**: Rotas FastAPI + Templates Jinja2 + HTMX + Chart.js + CSS limpo e responsivo.
- [x] **Etapa 5**: Suite de testes automatizados + validação ponta-a-ponta rodando o servidor localmente com CSVs reais de exemplo.
