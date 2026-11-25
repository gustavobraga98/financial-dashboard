from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import db_session
from app.services.rules import extract_installment, normalize_text, upsert_rule
from app.web import load_common_data, parse_optional_int, resolve_default_month, templates

router = APIRouter(prefix="/lancamentos")


def _fetch_tx_with_joins(conn, tx_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT t.*, a.name AS account_name, a.account_type, b.name AS bank_name, b.color AS bank_color,
               c.name AS category_name, c.color AS category_color
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        JOIN banks b ON b.id = a.bank_id
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.id = ?
        """,
        (tx_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("", response_class=HTMLResponse)
def transactions_page(
    request: Request,
    month: str | None = Query(default=None),
    bank_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    q: str = Query(default=""),
    show_raw: int = Query(default=0),
    msg: str | None = Query(default=None),
):
    parsed_bank = parse_optional_int(bank_id)
    parsed_account = parse_optional_int(account_id)

    with db_session() as conn:
        common = load_common_data(conn)
        if month == "all":
            selected_month = "all"
        else:
            selected_month = resolve_default_month(conn, month)
            if selected_month not in common["months"]:
                common["months"] = sorted({*common["months"], selected_month}, reverse=True)

        where = ["1=1"]
        params: list = []

        if selected_month != "all":
            where.append("t.competence_month = ?")
            params.append(selected_month)
        if parsed_account is not None:
            where.append("t.account_id = ?")
            params.append(parsed_account)
        elif parsed_bank is not None:
            where.append("a.bank_id = ?")
            params.append(parsed_bank)

        if category_id == "none":
            where.append("t.category_id IS NULL")
        else:
            parsed_cat = parse_optional_int(category_id)
            if parsed_cat is not None:
                where.append("t.category_id = ?")
                params.append(parsed_cat)

        if kind in ("expense", "income", "transfer"):
            where.append("t.kind = ?")
            params.append(kind)

        rows = conn.execute(
            f"""
            SELECT t.*, a.name AS account_name, a.account_type, b.name AS bank_name, b.color AS bank_color,
                   c.name AS category_name, c.color AS category_color
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            JOIN banks b ON b.id = a.bank_id
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE {' AND '.join(where)}
            ORDER BY t.raw_date DESC, t.id DESC
            """,
            params,
        ).fetchall()

        txs = [dict(r) for r in rows]

        # Accent-insensitive search across clean name, raw bank description, and notes
        search_norm = normalize_text(q)
        if search_norm:
            txs = [
                t
                for t in txs
                if search_norm in normalize_text(t["display_name"])
                or search_norm in normalize_text(t["raw_description"])
                or search_norm in normalize_text(t["notes"])
            ]

        totals = {
            "count": len(txs),
            "income_cents": sum(abs(t["raw_amount_cents"]) for t in txs if t["kind"] == "income"),
            "expense_cents": sum(abs(t["raw_amount_cents"]) for t in txs if t["kind"] == "expense"),
            "transfer_cents": sum(abs(t["raw_amount_cents"]) for t in txs if t["kind"] == "transfer"),
        }

    return templates.TemplateResponse(
        request,
        "transactions.html",
        {
            "active_nav": "transactions",
            "selected_month": selected_month,
            "selected_bank_id": parsed_bank,
            "selected_account_id": parsed_account,
            "selected_category_id": category_id or "",
            "selected_kind": kind or "",
            "q": q,
            "show_raw": bool(show_raw),
            "transactions": txs,
            "totals": totals,
            "flash_msg": msg,
            **common,
        },
    )


@router.get("/{tx_id}/row", response_class=HTMLResponse)
def transaction_row_partial(request: Request, tx_id: int, show_raw: int = Query(default=0)):
    with db_session() as conn:
        tx = _fetch_tx_with_joins(conn, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return templates.TemplateResponse(
        request,
        "partials/tx_row.html",
        {"tx": tx, "show_raw": bool(show_raw)},
    )


@router.get("/{tx_id}/edit", response_class=HTMLResponse)
def transaction_edit_partial(request: Request, tx_id: int, show_raw: int = Query(default=0)):
    with db_session() as conn:
        tx = _fetch_tx_with_joins(conn, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
        categories = [
            dict(r)
            for r in conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
        ]
    _, _, suggested_pattern = extract_installment(tx["raw_description"])
    return templates.TemplateResponse(
        request,
        "partials/tx_edit_row.html",
        {
            "tx": tx,
            "categories": categories,
            "suggested_pattern": suggested_pattern,
            "show_raw": bool(show_raw),
        },
    )


@router.post("/{tx_id}")
def update_transaction(
    request: Request,
    tx_id: int,
    display_name: str = Form(...),
    category_id: str = Form(default=""),
    kind: str = Form(...),
    competence_month: str = Form(...),
    notes: str = Form(default=""),
    save_rule: str | None = Form(default=None),
    rule_match_type: str = Form(default="contains"),
    rule_pattern: str = Form(default=""),
    apply_existing: str | None = Form(default=None),
    show_raw: int = Form(default=0),
):
    parsed_cat = parse_optional_int(category_id)
    clean_name = display_name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Nome não pode ficar vazio")
    if kind not in ("expense", "income", "transfer"):
        raise HTTPException(status_code=400, detail="Tipo inválido")

    retro_updated = 0
    with db_session() as conn:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")

        conn.execute(
            """
            UPDATE transactions
            SET display_name = ?, category_id = ?, kind = ?, competence_month = ?, notes = ?
            WHERE id = ?
            """,
            (clean_name, parsed_cat, kind, competence_month.strip(), notes.strip(), tx_id),
        )

        if save_rule:
            pattern = rule_pattern.strip() or existing["raw_description"]
            _, retro_updated = upsert_rule(
                conn,
                pattern=pattern,
                match_type=rule_match_type,
                target_display_name=clean_name,
                target_category_id=parsed_cat,
                target_kind=kind,
                apply_existing=bool(apply_existing),
            )

        tx = _fetch_tx_with_joins(conn, tx_id)

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        resp = templates.TemplateResponse(
            request,
            "partials/tx_row.html",
            {"tx": tx, "show_raw": bool(show_raw), "just_saved": True, "retro_updated": retro_updated},
        )
        if retro_updated > 1:
            resp.headers["HX-Refresh"] = "true"
        return resp
    return RedirectResponse(url="/lancamentos", status_code=303)


@router.delete("/{tx_id}")
def delete_transaction(request: Request, tx_id: int):
    with db_session() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200)
    return RedirectResponse(url="/lancamentos", status_code=303)
