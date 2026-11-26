# Dashboard Financeiro Local

Aplicação 100% local para controle financeiro pessoal a partir de extratos CSV de múltiplos bancos e cartões de crédito.

## Como rodar

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000) no navegador.

## Testes

```bash
uv run pytest
```

Consulte [docs/SPEC.md](docs/SPEC.md) para a especificação completa da arquitetura e regras de negócio.
