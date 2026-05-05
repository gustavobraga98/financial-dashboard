# Dashboard Financeiro

Um dashboard financeiro simples e moderno para gerenciar suas finanças pessoais.

## Tecnologias

- **Backend**: FastAPI
- **Frontend**: Streamlit
- **Banco de Dados**: SQLite
- **Gerenciador de Pacotes**: [uv](https://github.com/astral-sh/uv)

## Como rodar

### 1. Instalar dependências

Certifique-se de ter o `uv` instalado.

```bash
uv sync
```

### 2. Rodar o Backend

```bash
uv run uvicorn backend.main:app --reload
```

O backend estará disponível em `http://localhost:8000`.

### 3. Rodar o Frontend

```bash
uv run streamlit run frontend/main.py
```

O frontend estará disponível em `http://localhost:8501`.

## Estrutura do Projeto

- `backend/`: Código do servidor FastAPI.
- `frontend/`: Código da interface Streamlit.
- `sql_app.db`: Arquivo do banco de Dados SQLite (gerado automaticamente).
