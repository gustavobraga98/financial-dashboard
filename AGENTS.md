# AGENTS.md

Guia de referência rápida para desenvolvimento e manutenção deste projeto.

## Visão Geral

Aplicação web **100% local**, single-user, sem autenticação, para organização financeira pessoal a partir de extratos CSV exportados de bancos e cartões de crédito.

## Stack

- **Backend & Views**: Python 3.12+, FastAPI, Jinja2, HTMX (vendorizado offline), Chart.js (vendorizado offline)
- **Banco de Dados**: SQLite (`data/finances.db`) via `sqlite3` padrão (sem ORM pesado)
- **Gerenciador de Pacotes**: `uv` (sempre rodar via `uv run ...`)
- **Idioma & Moeda da UI**: Português (`pt-BR`) e BRL (`R$ 1.234,56`)

## Comandos Úteis

```bash
# Instalar/sincronizar dependências
uv sync

# Rodar servidor local (desenvolvimento)
uv run uvicorn app.main:app --reload --port 8000

# Rodar testes
uv run pytest
```

## Princípios de Arquitetura

1. **Simplicidade primeiro**: processo único Python, zero build JS, SQLite local, HTML server-rendered com HTMX para interações inline.
2. **Retro-validação sagrada**: campos originais do CSV (`raw_description`, `raw_date`, `raw_amount`) nunca são sobrescritos; renomeações ficam em `display_name`.
3. **Sem dupla contagem**: pagamentos de fatura e transferências entre contas próprias usam `kind = 'transfer'` (afetam o saldo da conta individual, mas não inflam Receitas/Despesas na visão consolidada).
4. **Mês de competência (`competence_month`)**: contas correntes usam o mês de `raw_date`; cartões de crédito associam a importação ao mês da fatura para casar exatamente com o valor mensal devido, mesmo quando parcelas mantêm a data original da compra.
5. **Regras & Parcelas**: normalização remove sufixos de parcela (`02/06`) para matching futuro; parcelas em cartão projetam automaticamente as parcelas futuras no planejamento mensal.

## Documentação

- Especificação completa e roadmap: [docs/SPEC.md](docs/SPEC.md)
