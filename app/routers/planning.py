from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import db_session
from app.formatting import parse_brl_to_cents, shift_month
from app.services.finance import get_lookahead, get_month_planning
from app.web import load_common_data, parse_optional_int, resolve_default_month, templates

router = APIRouter(prefix="/planejamento")


@router.get("", response_class=HTMLResponse)
def planning_page(
    request: Request,
    month: str | None = Query(default=None),
    bank_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    msg: str | None = Query(default=None),
):
    parsed_bank = parse_optional_int(bank_id)
    parsed_account = parse_optional_int(account_id)

    with db_session() as conn:
        common = load_common_data(conn)
        selected_month = resolve_default_month(conn, month)
        if selected_month not in common["months"]:
            common["months"] = sorted({*common["months"], selected_month}, reverse=True)

        plan = get_month_planning(
            conn,
            selected_month,
            bank_id=parsed_bank,
            account_id=parsed_account,
        )
        lookahead = get_lookahead(
            conn,
            selected_month,
            months=6,
            bank_id=parsed_bank,
            account_id=parsed_account,
        )

    lookahead_chart = {
        "labels": [m["month_short"] for m in lookahead],
        "expected_income": [round(m["expected_income_cents"] / 100, 2) for m in lookahead],
        "actual_expense": [round(m["actual_expense_cents"] / 100, 2) for m in lookahead],
        "pending_committed": [round(m["pending_committed_cents"] / 100, 2) for m in lookahead],
    }

    return templates.TemplateResponse(
        request,
        "planning.html",
        {
            "active_nav": "planning",
            "selected_month": selected_month,
            "prev_month": shift_month(selected_month, -1),
            "next_month": shift_month(selected_month, 1),
            "selected_bank_id": parsed_bank,
            "selected_account_id": parsed_account,
            "plan": plan,
            "lookahead": lookahead,
            "lookahead_chart_json": json.dumps(lookahead_chart, ensure_ascii=False),
            "flash_msg": msg,
            **common,
        },
    )


@router.post("/items")
def create_recurring_item(
    name: str = Form(...),
    kind: str = Form(...),
    expected_amount: str = Form(...),
    day_of_month: int = Form(default=5),
    account_id: str = Form(default=""),
    category_id: str = Form(default=""),
    match_keyword: str = Form(default=""),
    start_month: str = Form(default=""),
    end_month: str = Form(default=""),
    return_month: str = Form(default=""),
):
    cents = abs(parse_brl_to_cents(expected_amount))
    acc_id = parse_optional_int(account_id)
    cat_id = parse_optional_int(category_id)
    clean_kind = "income" if kind == "income" else "expense"
    day = max(1, min(31, int(day_of_month)))

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO recurring_items (
                name, kind, expected_amount_cents, day_of_month,
                account_id, category_id, match_keyword, start_month, end_month
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                clean_kind,
                cents,
                day,
                acc_id,
                cat_id,
                match_keyword.strip(),
                start_month.strip() or None,
                end_month.strip() or None,
            ),
        )

    suffix = f"?month={return_month}&msg={quote('Item adicionado ao planejamento.')}" if return_month else ""
    return RedirectResponse(url=f"/planejamento{suffix}", status_code=303)


@router.post("/items/{item_id}/status")
def set_recurring_status(
    item_id: int,
    month: str = Form(...),
    status: str = Form(...),
):
    with db_session() as conn:
        if status == "pending":
            conn.execute(
                "DELETE FROM recurring_matches WHERE recurring_item_id = ? AND competence_month = ?",
                (item_id, month),
            )
        elif status in ("paid", "skipped"):
            conn.execute(
                """
                INSERT INTO recurring_matches (recurring_item_id, competence_month, status)
                VALUES (?, ?, ?)
                ON CONFLICT(recurring_item_id, competence_month)
                DO UPDATE SET status = excluded.status, updated_at = datetime('now')
                """,
                (item_id, month, status),
            )
    return RedirectResponse(url=f"/planejamento?month={month}", status_code=303)


@router.post("/items/{item_id}/delete")
def delete_recurring_item(item_id: int, month: str = Form(default="")):
    with db_session() as conn:
        conn.execute("DELETE FROM recurring_items WHERE id = ?", (item_id,))
    suffix = f"?month={month}&msg={quote('Item removido.')}" if month else ""
    return RedirectResponse(url=f"/planejamento{suffix}", status_code=303)
