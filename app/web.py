from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

from app.formatting import (
    current_month,
    format_brl,
    format_brl_input,
    format_date_br,
    month_label,
)
from app.services.finance import list_available_months

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

templates.env.filters["brl"] = lambda v: format_brl(v, show_sign=False)
templates.env.filters["brl_signed"] = lambda v: format_brl(v, show_sign=True)
templates.env.filters["brl_input"] = format_brl_input
templates.env.filters["date_br"] = format_date_br
templates.env.filters["month_label"] = lambda m: month_label(m, short=False)
templates.env.filters["month_short"] = lambda m: month_label(m, short=True)


ACCOUNT_TYPE_LABELS = {
    "checking": "Conta Corrente",
    "credit_card": "Cartão de Crédito",
    "savings": "Poupança / Reserva",
}

KIND_LABELS = {
    "expense": "Despesa",
    "income": "Receita",
    "transfer": "Transferência / Fatura",
}

templates.env.globals["ACCOUNT_TYPE_LABELS"] = ACCOUNT_TYPE_LABELS
templates.env.globals["KIND_LABELS"] = KIND_LABELS


def parse_optional_int(raw: str | None) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def load_common_data(conn: sqlite3.Connection) -> dict[str, Any]:
    banks = [
        dict(r)
        for r in conn.execute("SELECT * FROM banks ORDER BY name ASC").fetchall()
    ]
    accounts = [
        dict(r)
        for r in conn.execute(
            """
            SELECT a.*, b.name AS bank_name, b.color AS bank_color
            FROM accounts a
            JOIN banks b ON b.id = a.bank_id
            ORDER BY b.name ASC, a.account_type ASC, a.name ASC
            """
        ).fetchall()
    ]
    categories = [
        dict(r)
        for r in conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
    ]
    months = list_available_months(conn)
    return {
        "banks": banks,
        "accounts": accounts,
        "categories": categories,
        "months": months,
    }


def resolve_default_month(conn: sqlite3.Connection, month: str | None) -> str:
    if month and len(month) == 7 and "-" in month:
        return month
    return current_month()
