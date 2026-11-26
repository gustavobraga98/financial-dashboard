from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import db_session
from app.formatting import parse_brl_to_cents, today_iso
from app.services.rules import reapply_all_rules, upsert_rule
from app.web import load_common_data, parse_optional_int, templates

router = APIRouter(prefix="/configuracoes")


@router.get("", response_class=HTMLResponse)
def settings_page(
    request: Request,
    tab: str = Query(default="accounts"),
    msg: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    with db_session() as conn:
        common = load_common_data(conn)
        rules = [
            dict(r)
            for r in conn.execute(
                """
                SELECT r.*, c.name AS category_name, c.color AS category_color
                FROM rules r
                LEFT JOIN categories c ON c.id = r.target_category_id
                ORDER BY r.priority ASC, r.id DESC
                """
            ).fetchall()
        ]
        profiles = [
            dict(r)
            for r in conn.execute(
                """
                SELECT p.*, a.name AS account_name, b.name AS bank_name
                FROM import_profiles p
                LEFT JOIN accounts a ON a.id = p.account_id
                LEFT JOIN banks b ON b.id = a.bank_id
                ORDER BY p.name ASC
                """
            ).fetchall()
        ]

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_nav": "settings",
            "active_tab": tab,
            "today_iso": today_iso(),
            "rules": rules,
            "profiles": profiles,
            "flash_msg": msg,
            "error_msg": error,
            **common,
        },
    )


@router.post("/banks")
def create_bank(name: str = Form(...), color: str = Form(default="#1B6B53")):
    clean = name.strip()
    if not clean:
        return RedirectResponse(url="/configuracoes?tab=accounts&error=" + quote("Informe o nome do banco."), status_code=303)
    try:
        with db_session() as conn:
            conn.execute("INSERT INTO banks (name, color) VALUES (?, ?)", (clean, color.strip() or "#1B6B53"))
    except Exception:
        return RedirectResponse(url="/configuracoes?tab=accounts&error=" + quote("Já existe um banco com esse nome."), status_code=303)
    return RedirectResponse(url="/configuracoes?tab=accounts&msg=" + quote(f"Banco '{clean}' adicionado."), status_code=303)


@router.post("/banks/{bank_id}/delete")
def delete_bank(bank_id: int):
    with db_session() as conn:
        conn.execute("DELETE FROM banks WHERE id = ?", (bank_id,))
    return RedirectResponse(url="/configuracoes?tab=accounts&msg=" + quote("Banco removido."), status_code=303)


@router.post("/accounts")
def create_account(
    bank_id: int = Form(...),
    name: str = Form(...),
    account_type: str = Form(...),
    initial_balance: str = Form(default="0"),
    initial_balance_date: str = Form(default=""),
):
    clean = name.strip()
    if not clean:
        return RedirectResponse(url="/configuracoes?tab=accounts&error=" + quote("Informe o nome da conta."), status_code=303)
    if account_type not in ("checking", "credit_card", "savings"):
        account_type = "checking"
    if account_type == "credit_card":
        bal_cents = 0
        bal_date = None
    else:
        bal_cents = parse_brl_to_cents(initial_balance) if initial_balance.strip() else 0
        bal_date = initial_balance_date.strip() or None

    try:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO accounts (bank_id, name, account_type, initial_balance_cents, initial_balance_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (bank_id, clean, account_type, bal_cents, bal_date),
            )
    except Exception:
        return RedirectResponse(url="/configuracoes?tab=accounts&error=" + quote("Essa conta já existe nesse banco."), status_code=303)
    return RedirectResponse(url="/configuracoes?tab=accounts&msg=" + quote(f"Conta '{clean}' criada."), status_code=303)


@router.post("/accounts/{account_id}/balance")
def update_account_balance(
    account_id: int,
    initial_balance: str = Form(default="0"),
    initial_balance_date: str = Form(default=""),
):
    bal_cents = parse_brl_to_cents(initial_balance) if initial_balance.strip() else 0
    bal_date = initial_balance_date.strip() or None
    with db_session() as conn:
        conn.execute(
            """
            UPDATE accounts
            SET initial_balance_cents = ?, initial_balance_date = ?
            WHERE id = ?
            """,
            (bal_cents, bal_date, account_id),
        )
    return RedirectResponse(url="/configuracoes?tab=accounts&msg=" + quote("Saldo de referência atualizado."), status_code=303)


@router.post("/accounts/{account_id}/delete")
def delete_account(account_id: int):
    with db_session() as conn:
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return RedirectResponse(url="/configuracoes?tab=accounts&msg=" + quote("Conta removida."), status_code=303)


@router.post("/categories")
def create_category(
    name: str = Form(...),
    color: str = Form(default="#2563EB"),
    monthly_budget: str = Form(default=""),
):
    clean = name.strip()
    budget_cents = abs(parse_brl_to_cents(monthly_budget)) if monthly_budget.strip() else None
    try:
        with db_session() as conn:
            conn.execute(
                "INSERT INTO categories (name, color, monthly_budget_cents) VALUES (?, ?, ?)",
                (clean, color.strip() or "#2563EB", budget_cents),
            )
    except Exception:
        return RedirectResponse(url="/configuracoes?tab=categories&error=" + quote("Categoria já existe."), status_code=303)
    return RedirectResponse(url="/configuracoes?tab=categories&msg=" + quote(f"Categoria '{clean}' criada."), status_code=303)


@router.post("/categories/{category_id}")
def update_category(
    category_id: int,
    color: str = Form(default="#2563EB"),
    monthly_budget: str = Form(default=""),
):
    budget_cents = abs(parse_brl_to_cents(monthly_budget)) if monthly_budget.strip() else None
    with db_session() as conn:
        conn.execute(
            "UPDATE categories SET color = ?, monthly_budget_cents = ? WHERE id = ?",
            (color.strip() or "#2563EB", budget_cents, category_id),
        )
    return RedirectResponse(url="/configuracoes?tab=categories&msg=" + quote("Categoria atualizada."), status_code=303)


@router.post("/categories/{category_id}/delete")
def delete_category(category_id: int):
    with db_session() as conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return RedirectResponse(url="/configuracoes?tab=categories&msg=" + quote("Categoria removida."), status_code=303)


@router.post("/rules")
def create_rule(
    pattern: str = Form(...),
    match_type: str = Form(default="contains"),
    target_display_name: str = Form(...),
    target_category_id: str = Form(default=""),
    target_kind: str = Form(default=""),
    apply_existing: str | None = Form(default=None),
):
    cat_id = parse_optional_int(target_category_id)
    kind = target_kind if target_kind in ("expense", "income", "transfer") else None
    with db_session() as conn:
        _, updated = upsert_rule(
            conn,
            pattern=pattern,
            match_type=match_type,
            target_display_name=target_display_name,
            target_category_id=cat_id,
            target_kind=kind,
            apply_existing=bool(apply_existing),
        )
    msg = f"Regra salva ({updated} lançamento(s) atualizado(s))."
    return RedirectResponse(url=f"/configuracoes?tab=rules&msg={quote(msg)}", status_code=303)


@router.post("/rules/reapply")
def reapply_rules_endpoint():
    with db_session() as conn:
        updated = reapply_all_rules(conn)
    msg = f"Regras reaplicadas em {updated} lançamento(s)."
    return RedirectResponse(url=f"/configuracoes?tab=rules&msg={quote(msg)}", status_code=303)


@router.post("/rules/{rule_id}/delete")
def delete_rule(rule_id: int):
    with db_session() as conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    return RedirectResponse(url="/configuracoes?tab=rules&msg=" + quote("Regra removida."), status_code=303)


@router.post("/profiles/{profile_id}/delete")
def delete_profile(profile_id: int):
    with db_session() as conn:
        conn.execute("DELETE FROM import_profiles WHERE id = ?", (profile_id,))
    return RedirectResponse(url="/configuracoes?tab=profiles&msg=" + quote("Perfil removido."), status_code=303)
