from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.db import db_session
from app.services.finance import get_dashboard_summary
from app.web import load_common_data, parse_optional_int, resolve_default_month, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    month: str | None = Query(default=None),
    bank_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
):
    parsed_bank = parse_optional_int(bank_id)
    parsed_account = parse_optional_int(account_id)

    with db_session() as conn:
        common = load_common_data(conn)
        selected_month = resolve_default_month(conn, month)
        if selected_month not in common["months"]:
            common["months"] = sorted({*common["months"], selected_month}, reverse=True)

        summary = get_dashboard_summary(
            conn,
            selected_month,
            bank_id=parsed_bank,
            account_id=parsed_account,
        )

    scope_label = "Todos os bancos"
    if parsed_account:
        acc = next((a for a in common["accounts"] if a["id"] == parsed_account), None)
        if acc:
            scope_label = f"{acc['bank_name']} · {acc['name']}"
    elif parsed_bank:
        bk = next((b for b in common["banks"] if b["id"] == parsed_bank), None)
        if bk:
            scope_label = bk["name"]

    chart_categories = {
        "labels": [c["name"] for c in summary["category_breakdown"][:10]],
        "values": [round(c["spent_cents"] / 100, 2) for c in summary["category_breakdown"][:10]],
        "colors": [c["color"] for c in summary["category_breakdown"][:10]],
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_nav": "dashboard",
            "selected_month": selected_month,
            "selected_bank_id": parsed_bank,
            "selected_account_id": parsed_account,
            "scope_label": scope_label,
            "summary": summary,
            "chart_categories_json": json.dumps(chart_categories, ensure_ascii=False),
            **common,
        },
    )
