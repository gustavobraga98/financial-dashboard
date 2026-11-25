from __future__ import annotations

import sqlite3
from typing import Any

from app.formatting import current_month, month_label, months_between, shift_month
from app.services.rules import normalize_text


def _scope_clause(
    bank_id: int | None = None,
    account_id: int | None = None,
    tx_alias: str = "t",
    acc_alias: str = "a",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if account_id is not None:
        clauses.append(f"{tx_alias}.account_id = ?")
        params.append(account_id)
    elif bank_id is not None:
        clauses.append(f"{acc_alias}.bank_id = ?")
        params.append(bank_id)
    return (" AND ".join(clauses) if clauses else "1=1"), params


def list_available_months(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT competence_month FROM transactions ORDER BY competence_month DESC"
    ).fetchall()
    months = {r["competence_month"] for r in rows}
    cur = current_month()
    months.add(cur)
    months.add(shift_month(cur, 1))
    months.add(shift_month(cur, -1))
    return sorted(months, reverse=True)


def compute_account_balances(
    conn: sqlite3.Connection,
    month: str,
    bank_id: int | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    where_parts = ["1=1"]
    params: list[Any] = []
    if account_id is not None:
        where_parts.append("a.id = ?")
        params.append(account_id)
    elif bank_id is not None:
        where_parts.append("a.bank_id = ?")
        params.append(bank_id)

    accounts = conn.execute(
        f"""
        SELECT a.*, b.name AS bank_name, b.color AS bank_color
        FROM accounts a
        JOIN banks b ON b.id = a.bank_id
        WHERE {' AND '.join(where_parts)}
        ORDER BY b.name ASC, a.account_type ASC, a.name ASC
        """,
        params,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for acc in accounts:
        if acc["account_type"] == "credit_card":
            row = conn.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN kind = 'expense' THEN ABS(raw_amount_cents) ELSE 0 END), 0) AS bill_cents,
                       COUNT(*) AS tx_count
                FROM transactions
                WHERE account_id = ? AND competence_month = ?
                """,
                (acc["id"], month),
            ).fetchone()
            results.append(
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "bank_id": acc["bank_id"],
                    "bank_name": acc["bank_name"],
                    "bank_color": acc["bank_color"],
                    "account_type": acc["account_type"],
                    "balance_cents": -int(row["bill_cents"]),
                    "bill_cents": int(row["bill_cents"]),
                    "tx_count": int(row["tx_count"]),
                    "initial_balance_cents": acc["initial_balance_cents"],
                    "initial_balance_date": acc["initial_balance_date"],
                }
            )
        else:
            date_filter = ""
            q_params: list[Any] = [acc["id"], month]
            if acc["initial_balance_date"]:
                date_filter = "AND raw_date >= ?"
                q_params.append(acc["initial_balance_date"])

            # Transfers affect an account's real cash balance, so sum raw_amount_cents across all kinds
            delta_row = conn.execute(
                f"""
                SELECT COALESCE(SUM(raw_amount_cents), 0) AS delta_cents,
                       COUNT(*) AS tx_count
                FROM transactions
                WHERE account_id = ?
                  AND competence_month <= ?
                  {date_filter}
                """,
                q_params,
            ).fetchone()

            month_flow = conn.execute(
                """
                SELECT COALESCE(SUM(raw_amount_cents), 0) AS flow_cents
                FROM transactions
                WHERE account_id = ? AND competence_month = ?
                """,
                (acc["id"], month),
            ).fetchone()

            bal = int(acc["initial_balance_cents"]) + int(delta_row["delta_cents"])
            results.append(
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "bank_id": acc["bank_id"],
                    "bank_name": acc["bank_name"],
                    "bank_color": acc["bank_color"],
                    "account_type": acc["account_type"],
                    "balance_cents": bal,
                    "month_flow_cents": int(month_flow["flow_cents"]),
                    "tx_count": int(delta_row["tx_count"]),
                    "initial_balance_cents": acc["initial_balance_cents"],
                    "initial_balance_date": acc["initial_balance_date"],
                }
            )
    return results


def project_installments_for_month(
    conn: sqlite3.Connection,
    target_month: str,
    bank_id: int | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    scope_sql, scope_params = _scope_clause(bank_id, account_id)

    # Fetch all installment transactions strictly prior to target_month
    rows = conn.execute(
        f"""
        SELECT t.*, a.name AS account_name, a.bank_id, b.name AS bank_name,
               c.name AS category_name, c.color AS category_color
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        JOIN banks b ON b.id = a.bank_id
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE {scope_sql}
          AND t.kind = 'expense'
          AND t.installment_current IS NOT NULL
          AND t.installment_total IS NOT NULL
          AND t.installment_current < t.installment_total
          AND t.installment_group_key IS NOT NULL
          AND t.competence_month < ?
        ORDER BY t.competence_month DESC, t.installment_current DESC, t.id DESC
        """,
        [*scope_params, target_month],
    ).fetchall()

    # Keep only the latest observed installment per (account_id, installment_group_key)
    latest_by_group: dict[tuple[int, str], sqlite3.Row] = {}
    for r in rows:
        key = (r["account_id"], r["installment_group_key"])
        if key not in latest_by_group:
            latest_by_group[key] = r

    # Check which installment groups are already present in target_month
    existing_rows = conn.execute(
        f"""
        SELECT t.account_id, t.installment_group_key
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE {scope_sql}
          AND t.competence_month = ?
          AND t.installment_group_key IS NOT NULL
        """,
        [*scope_params, target_month],
    ).fetchall()
    already_imported = {(r["account_id"], r["installment_group_key"]) for r in existing_rows}

    projected: list[dict[str, Any]] = []
    for key, src in latest_by_group.items():
        if key in already_imported:
            continue
        diff = months_between(src["competence_month"], target_month)
        if diff <= 0:
            continue
        proj_curr = int(src["installment_current"]) + diff
        total = int(src["installment_total"])
        if proj_curr > total:
            continue
        projected.append(
            {
                "display_name": src["display_name"],
                "account_id": src["account_id"],
                "account_name": src["account_name"],
                "bank_name": src["bank_name"],
                "category_name": src["category_name"] or "Sem categoria",
                "category_color": src["category_color"] or "#64748B",
                "amount_cents": abs(int(src["raw_amount_cents"])),
                "installment_current": proj_curr,
                "installment_total": total,
                "installment_label": f"{proj_curr:02d}/{total:02d}",
                "source_month": src["competence_month"],
            }
        )

    projected.sort(key=lambda x: (-x["amount_cents"], x["display_name"]))
    return projected


def get_month_planning(
    conn: sqlite3.Connection,
    month: str,
    bank_id: int | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    scope_sql, scope_params = _scope_clause(bank_id, account_id)

    # Actuals in the month
    actual_rows = conn.execute(
        f"""
        SELECT t.*, a.name AS account_name, a.bank_id
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE {scope_sql} AND t.competence_month = ?
        """,
        [*scope_params, month],
    ).fetchall()

    actual_income_cents = sum(
        abs(int(r["raw_amount_cents"])) for r in actual_rows if r["kind"] == "income"
    )
    actual_expense_cents = sum(
        abs(int(r["raw_amount_cents"])) for r in actual_rows if r["kind"] == "expense"
    )

    # Recurring items filtered by scope (items without account_id show in global view or when not scoped to a different bank)
    rec_where = ["r.active = 1"]
    rec_params: list[Any] = []
    if account_id is not None:
        rec_where.append("r.account_id = ?")
        rec_params.append(account_id)
    elif bank_id is not None:
        rec_where.append("a.bank_id = ?")
        rec_params.append(bank_id)

    recurring_rows = conn.execute(
        f"""
        SELECT r.*, a.name AS account_name, b.name AS bank_name,
               c.name AS category_name, c.color AS category_color
        FROM recurring_items r
        LEFT JOIN accounts a ON a.id = r.account_id
        LEFT JOIN banks b ON b.id = a.bank_id
        LEFT JOIN categories c ON c.id = r.category_id
        WHERE {' AND '.join(rec_where)}
        ORDER BY r.kind DESC, r.day_of_month ASC, r.name ASC
        """,
        rec_params,
    ).fetchall()

    explicit_matches = {
        m["recurring_item_id"]: m
        for m in conn.execute(
            "SELECT * FROM recurring_matches WHERE competence_month = ?",
            (month,),
        ).fetchall()
    }

    used_tx_ids: set[int] = {
        int(m["transaction_id"])
        for m in explicit_matches.values()
        if m["transaction_id"] is not None
    }

    recurring_incomes: list[dict[str, Any]] = []
    recurring_expenses: list[dict[str, Any]] = []
    pending_recurring_income_cents = 0
    pending_recurring_expense_cents = 0

    for item in recurring_rows:
        if item["start_month"] and month < item["start_month"]:
            continue
        if item["end_month"] and month > item["end_month"]:
            continue

        match = explicit_matches.get(item["id"])
        status = "pending"
        matched_tx = None
        actual_matched_cents = None

        if match:
            status = match["status"]  # 'paid' or 'skipped'
            actual_matched_cents = match["actual_amount_cents"]
            if match["transaction_id"]:
                matched_tx = next(
                    (t for t in actual_rows if t["id"] == match["transaction_id"]),
                    None,
                )
        else:
            # Try automatic keyword match against transactions in this month
            kw = normalize_text(item["match_keyword"] or item["name"])
            if kw:
                for tx in actual_rows:
                    if tx["id"] in used_tx_ids or tx["kind"] != item["kind"]:
                        continue
                    if item["account_id"] and tx["account_id"] != item["account_id"]:
                        continue
                    haystack = normalize_text(tx["display_name"]) + " " + normalize_text(tx["raw_description"])
                    if kw in haystack:
                        status = "auto_paid"
                        matched_tx = tx
                        actual_matched_cents = abs(int(tx["raw_amount_cents"]))
                        used_tx_ids.add(int(tx["id"]))
                        break

        entry = {
            "id": item["id"],
            "name": item["name"],
            "kind": item["kind"],
            "expected_amount_cents": int(item["expected_amount_cents"]),
            "day_of_month": item["day_of_month"],
            "account_id": item["account_id"],
            "account_name": item["account_name"],
            "bank_name": item["bank_name"],
            "category_name": item["category_name"] or "Sem categoria",
            "category_color": item["category_color"] or "#64748B",
            "match_keyword": item["match_keyword"],
            "status": status,
            "matched_tx_id": matched_tx["id"] if matched_tx else None,
            "matched_tx_name": matched_tx["display_name"] if matched_tx else None,
            "actual_amount_cents": actual_matched_cents,
        }

        if item["kind"] == "income":
            recurring_incomes.append(entry)
            if status == "pending":
                pending_recurring_income_cents += entry["expected_amount_cents"]
        else:
            recurring_expenses.append(entry)
            if status == "pending":
                pending_recurring_expense_cents += entry["expected_amount_cents"]

    projected_installments = project_installments_for_month(
        conn, month, bank_id=bank_id, account_id=account_id
    )
    projected_installments_cents = sum(p["amount_cents"] for p in projected_installments)

    expected_income_cents = actual_income_cents + pending_recurring_income_cents
    pending_committed_cents = pending_recurring_expense_cents + projected_installments_cents
    total_committed_cents = actual_expense_cents + pending_committed_cents
    available_cents = expected_income_cents - total_committed_cents

    committed_pct = (
        round((total_committed_cents / expected_income_cents) * 100, 1)
        if expected_income_cents > 0
        else (100.0 if total_committed_cents > 0 else 0.0)
    )
    actual_pct = (
        round((actual_expense_cents / expected_income_cents) * 100, 1)
        if expected_income_cents > 0
        else 0.0
    )
    pending_pct = (
        round((pending_committed_cents / expected_income_cents) * 100, 1)
        if expected_income_cents > 0
        else 0.0
    )

    return {
        "month": month,
        "month_label": month_label(month),
        "actual_income_cents": actual_income_cents,
        "pending_recurring_income_cents": pending_recurring_income_cents,
        "expected_income_cents": expected_income_cents,
        "actual_expense_cents": actual_expense_cents,
        "pending_recurring_expense_cents": pending_recurring_expense_cents,
        "projected_installments_cents": projected_installments_cents,
        "pending_committed_cents": pending_committed_cents,
        "total_committed_cents": total_committed_cents,
        "available_cents": available_cents,
        "committed_pct": committed_pct,
        "actual_pct": actual_pct,
        "pending_pct": pending_pct,
        "recurring_incomes": recurring_incomes,
        "recurring_expenses": recurring_expenses,
        "projected_installments": projected_installments,
    }


def get_lookahead(
    conn: sqlite3.Connection,
    start_month: str,
    months: int = 6,
    bank_id: int | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    result = []
    for offset in range(months):
        m = shift_month(start_month, offset)
        plan = get_month_planning(conn, m, bank_id=bank_id, account_id=account_id)
        plan["month_short"] = month_label(m, short=True)
        result.append(plan)
    return result


def get_dashboard_summary(
    conn: sqlite3.Connection,
    month: str,
    bank_id: int | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    scope_sql, scope_params = _scope_clause(bank_id, account_id)

    totals = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN t.kind = 'income' THEN ABS(t.raw_amount_cents) ELSE 0 END), 0) AS income_cents,
            COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN ABS(t.raw_amount_cents) ELSE 0 END), 0) AS expense_cents,
            COALESCE(SUM(CASE WHEN t.kind = 'transfer' THEN ABS(t.raw_amount_cents) ELSE 0 END), 0) AS transfer_cents,
            COUNT(*) AS tx_count
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE {scope_sql} AND t.competence_month = ?
        """,
        [*scope_params, month],
    ).fetchone()

    income_cents = int(totals["income_cents"])
    expense_cents = int(totals["expense_cents"])
    transfer_cents = int(totals["transfer_cents"])
    net_cents = income_cents - expense_cents

    # Spending by category (plus categories that have budgets even if 0 spent)
    cat_spend_rows = conn.execute(
        f"""
        SELECT
            COALESCE(c.id, 0) AS category_id,
            COALESCE(c.name, 'Sem categoria') AS name,
            COALESCE(c.color, '#94A3B8') AS color,
            c.monthly_budget_cents AS budget_cents,
            COALESCE(SUM(ABS(t.raw_amount_cents)), 0) AS spent_cents,
            COUNT(*) AS tx_count
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE {scope_sql}
          AND t.competence_month = ?
          AND t.kind = 'expense'
        GROUP BY COALESCE(c.id, 0), COALESCE(c.name, 'Sem categoria'), COALESCE(c.color, '#94A3B8'), c.monthly_budget_cents
        ORDER BY spent_cents DESC
        """,
        [*scope_params, month],
    ).fetchall()

    category_breakdown = [
        {
            "category_id": r["category_id"],
            "name": r["name"],
            "color": r["color"],
            "spent_cents": int(r["spent_cents"]),
            "budget_cents": r["budget_cents"],
            "tx_count": int(r["tx_count"]),
            "share_pct": round((int(r["spent_cents"]) / expense_cents) * 100, 1) if expense_cents > 0 else 0.0,
        }
        for r in cat_spend_rows
    ]

    # Budget progress: all categories with a monthly budget configured
    spent_by_cat_id = {c["category_id"]: c["spent_cents"] for c in category_breakdown}
    budget_rows = conn.execute(
        """
        SELECT id, name, color, monthly_budget_cents
        FROM categories
        WHERE monthly_budget_cents IS NOT NULL AND monthly_budget_cents > 0
        ORDER BY name ASC
        """
    ).fetchall()

    budgets = []
    for b in budget_rows:
        spent = spent_by_cat_id.get(b["id"], 0)
        limit_c = int(b["monthly_budget_cents"])
        pct = round((spent / limit_c) * 100, 1) if limit_c > 0 else 0.0
        budgets.append(
            {
                "id": b["id"],
                "name": b["name"],
                "color": b["color"],
                "spent_cents": spent,
                "budget_cents": limit_c,
                "remaining_cents": limit_c - spent,
                "pct": pct,
                "bar_pct": min(pct, 100.0),
                "status": "over" if spent > limit_c else ("warn" if pct >= 80 else "ok"),
            }
        )
    budgets.sort(key=lambda x: -x["pct"])

    # Account balances & credit card bills
    accounts = compute_account_balances(conn, month, bank_id=bank_id, account_id=account_id)
    total_cash_cents = sum(
        a["balance_cents"] for a in accounts if a["account_type"] in ("checking", "savings")
    )
    total_credit_bill_cents = sum(
        a["bill_cents"] for a in accounts if a["account_type"] == "credit_card"
    )

    # Monthly commitment planning
    planning = get_month_planning(conn, month, bank_id=bank_id, account_id=account_id)

    # Bank segmentation summary (only meaningful on global view, still useful always)
    bank_rows = conn.execute(
        """
        SELECT
            b.id, b.name, b.color,
            COALESCE(SUM(CASE WHEN t.kind = 'income' THEN ABS(t.raw_amount_cents) ELSE 0 END), 0) AS income_cents,
            COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN ABS(t.raw_amount_cents) ELSE 0 END), 0) AS expense_cents,
            COUNT(t.id) AS tx_count
        FROM banks b
        LEFT JOIN accounts a ON a.bank_id = b.id
        LEFT JOIN transactions t ON t.account_id = a.id AND t.competence_month = ?
        GROUP BY b.id, b.name, b.color
        ORDER BY expense_cents DESC, b.name ASC
        """,
        (month,),
    ).fetchall()

    # Recent transactions in scope
    recent_txs = conn.execute(
        f"""
        SELECT t.*, a.name AS account_name, a.account_type, b.name AS bank_name, b.color AS bank_color,
               c.name AS category_name, c.color AS category_color
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        JOIN banks b ON b.id = a.bank_id
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE {scope_sql} AND t.competence_month = ?
        ORDER BY t.raw_date DESC, t.id DESC
        LIMIT 12
        """,
        [*scope_params, month],
    ).fetchall()

    return {
        "month": month,
        "month_label": month_label(month),
        "prev_month": shift_month(month, -1),
        "next_month": shift_month(month, 1),
        "income_cents": income_cents,
        "expense_cents": expense_cents,
        "transfer_cents": transfer_cents,
        "net_cents": net_cents,
        "tx_count": int(totals["tx_count"]),
        "category_breakdown": category_breakdown,
        "budgets": budgets,
        "accounts": accounts,
        "total_cash_cents": total_cash_cents,
        "total_credit_bill_cents": total_credit_bill_cents,
        "planning": planning,
        "bank_summary": [dict(r) for r in bank_rows],
        "recent_txs": [dict(r) for r in recent_txs],
    }
