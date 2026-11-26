# Dashboard Financeiro Local

Aplicação 100% local para controle financeiro pessoal a partir de extratos CSV de múltiplos bancos e cartões de crédito.

## Como rodar

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000) no navegador.

## Como rodar com Docker

```bash
docker compose up -d --build
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000) no navegador. Os dados ficam persistidos localmente em `./data/finances.db`.

Para parar o container:

```bash
docker compose down
```

Para usar outra porta local (por exemplo, `8080`):

```bash
PORT=8080 docker compose up -d
```

## Testes

```bash
uv run pytest
```

Consulte [docs/SPEC.md](docs/SPEC.md) para a especificação completa da arquitetura e regras de negócio.
