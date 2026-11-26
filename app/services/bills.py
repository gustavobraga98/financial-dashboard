from __future__ import annotations

import sqlite3
from typing import Any


def _valid_month(value: str) -> bool:
    if len(value) != 7 or value[4] != "-":
        return False
    y, m = value[:4], value[5:]
    if not (y.isdigit() and m.isdigit()):
        return False
    return 1 <= int(m) <= 12


def compute_card_bill_net_cents(
    conn: sqlite3.Connection, card_account_id: int, competence_month: str
) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(
                   CASE WHEN kind = 'expense' THEN ABS(raw_amount_cents)
                        WHEN kind = 'income' THEN -ABS(raw_amount_cents)
                        ELSE 0 END
               ), 0) AS bill_cents,
               COALESCE(SUM(CASE WHEN kind IN ('expense', 'income') THEN 1 ELSE 0 END), 0) AS item_count
        FROM transactions
        WHERE account_id = ? AND competence_month = ?
        """,
        (card_account_id, competence_month),
    ).fetchone()
    return int(row["bill_cents"]), int(row["item_count"])


def _linked_paid(
    conn: sqlite3.Connection,
    card_account_id: int,
    competence_month: str,
    exclude_tx_id: int | None = None,
) -> tuple[int, int]:
    sql = """
        SELECT COALESCE(SUM(ABS(t.raw_amount_cents)), 0) AS paid, COUNT(*) AS n
        FROM bill_payment_links l
        JOIN transactions t ON t.id = l.payment_transaction_id
        WHERE l.card_account_id = ? AND l.competence_month = ?
    """
    params: list[Any] = [card_account_id, competence_month]
    if exclude_tx_id is not None:
        sql += " AND l.payment_transaction_id != ?"
        params.append(exclude_tx_id)
    row = conn.execute(sql, params).fetchone()
    return int(row["paid"]), int(row["n"])


def get_bill_reconciliation(
    conn: sqlite3.Connection, card_account_id: int, competence_month: str
) -> dict[str, Any] | None:
    card = conn.execute(
        """
        SELECT a.id, a.name, b.name AS bank_name, b.color AS bank_color
        FROM accounts a JOIN banks b ON b.id = a.bank_id
        WHERE a.id = ?
        """,
        (card_account_id,),
    ).fetchone()
    if not card:
        return None
    bill_cents, item_count = compute_card_bill_net_cents(conn, card_account_id, competence_month)
    paid_cents, payment_count = _linked_paid(conn, card_account_id, competence_month)
    diff_cents = paid_cents - bill_cents
    if item_count == 0:
        status = "empty"
    elif diff_cents == 0:
        status = "matched"
    else:
        status = "diff"
    return {
        "card_account_id": int(card["id"]),
        "card_account_name": card["name"],
        "card_bank_name": card["bank_name"],
        "card_bank_color": card["bank_color"],
        "competence_month": competence_month,
        "item_count": item_count,
        "bill_cents": bill_cents,
        "paid_cents": paid_cents,
        "diff_cents": diff_cents,
        "abs_diff_cents": abs(diff_cents),
        "payment_count": payment_count,
        "status": status,
    }


def link_payment_to_bill(
    conn: sqlite3.Connection, payment_tx_id: int, card_account_id: int, competence_month: str
) -> dict[str, Any]:
    tx = conn.execute(
        """
        SELECT t.id, t.raw_amount_cents, a.account_type
        FROM transactions t JOIN accounts a ON a.id = t.account_id
        WHERE t.id = ?
        """,
        (payment_tx_id,),
    ).fetchone()
    if not tx:
        raise ValueError("Lançamento não encontrado")
    if tx["account_type"] not in ("checking", "savings") or int(tx["raw_amount_cents"]) >= 0:
        raise ValueError("Só é possível vincular saídas de conta corrente/poupança")
    card = conn.execute(
        "SELECT id, account_type FROM accounts WHERE id = ?", (card_account_id,)
    ).fetchone()
    if not card or card["account_type"] != "credit_card":
        raise ValueError("Selecione uma conta de cartão de crédito")
    competence_month = (competence_month or "").strip()
    if not _valid_month(competence_month):
        raise ValueError("Mês de competência inválido (use AAAA-MM)")

    conn.execute(
        """
        INSERT INTO bill_payment_links (payment_transaction_id, card_account_id, competence_month)
        VALUES (?, ?, ?)
        ON CONFLICT(payment_transaction_id) DO UPDATE SET
            card_account_id = excluded.card_account_id,
            competence_month = excluded.competence_month
        """,
        (payment_tx_id, card_account_id, competence_month),
    )
    conn.execute("UPDATE transactions SET kind = 'transfer' WHERE id = ?", (payment_tx_id,))
    result = get_bill_reconciliation(conn, card_account_id, competence_month)
    assert result is not None
    return result


def unlink_payment_from_bill(
    conn: sqlite3.Connection, payment_tx_id: int, *, revert_to_expense: bool = True
) -> bool:
    cur = conn.execute(
        "DELETE FROM bill_payment_links WHERE payment_transaction_id = ?", (payment_tx_id,)
    )
    removed = cur.rowcount > 0
    if removed and revert_to_expense:
        conn.execute(
            "UPDATE transactions SET kind = 'expense' WHERE id = ? AND kind = 'transfer'",
            (payment_tx_id,),
        )
    return removed


def reconcile_links_after_card_changes(
    conn: sqlite3.Connection, card_account_id: int, competence_month: str
) -> int:
    _, item_count = compute_card_bill_net_cents(conn, card_account_id, competence_month)
    if item_count > 0:
        return 0
    rows = conn.execute(
        """
        SELECT payment_transaction_id FROM bill_payment_links
        WHERE card_account_id = ? AND competence_month = ?
        """,
        (card_account_id, competence_month),
    ).fetchall()
    for r in rows:
        unlink_payment_from_bill(conn, int(r["payment_transaction_id"]), revert_to_expense=True)
    return len(rows)


def attach_bill_links_to_transactions(conn: sqlite3.Connection, txs: list[dict[str, Any]]) -> None:
    for tx in txs:
        tx["bill_link"] = None
    ids = [int(t["id"]) for t in txs if t.get("account_type") in ("checking", "savings")]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT payment_transaction_id, card_account_id, competence_month
        FROM bill_payment_links
        WHERE payment_transaction_id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    link_by_tx = {int(r["payment_transaction_id"]): r for r in rows}
    cache: dict[tuple[int, str], dict[str, Any] | None] = {}
    for tx in txs:
        link = link_by_tx.get(int(tx["id"]))
        if not link:
            continue
        key = (int(link["card_account_id"]), link["competence_month"])
        if key not in cache:
            cache[key] = get_bill_reconciliation(conn, key[0], key[1])
        tx["bill_link"] = cache[key]


def list_existing_card_bills(
    conn: sqlite3.Connection, *, card_account_id: int | None = None
) -> list[dict[str, Any]]:
    where = "a.account_type = 'credit_card' AND t.kind IN ('expense', 'income')"
    params: list[Any] = []
    if card_account_id is not None:
        where += " AND a.id = ?"
        params.append(card_account_id)
    rows = conn.execute(
        f"""
        SELECT a.id AS card_account_id, a.name AS card_account_name,
               b.name AS card_bank_name, b.color AS card_bank_color,
               t.competence_month AS competence_month
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        JOIN banks b ON b.id = a.bank_id
        WHERE {where}
        GROUP BY a.id, t.competence_month
        ORDER BY t.competence_month DESC, b.name ASC, a.name ASC
        """,
        params,
    ).fetchall()
    result = []
    for r in rows:
        bill_cents, item_count = compute_card_bill_net_cents(
            conn, int(r["card_account_id"]), r["competence_month"]
        )
        paid, _ = _linked_paid(conn, int(r["card_account_id"]), r["competence_month"])
        result.append(
            {
                "card_account_id": int(r["card_account_id"]),
                "card_account_name": r["card_account_name"],
                "card_bank_name": r["card_bank_name"],
                "card_bank_color": r["card_bank_color"],
                "competence_month": r["competence_month"],
                "item_count": item_count,
                "bill_cents": bill_cents,
                "already_linked_paid_cents": paid,
            }
        )
    return result


def get_payment_context_for_import(
    conn: sqlite3.Connection, payment_tx_id: int | None
) -> dict[str, Any] | None:
    if payment_tx_id is None:
        return None
    row = conn.execute(
        """
        SELECT t.*, a.name AS account_name, a.account_type, a.bank_id, b.name AS bank_name
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        JOIN banks b ON b.id = a.bank_id
        WHERE t.id = ?
        """,
        (payment_tx_id,),
    ).fetchone()
    if not row or row["account_type"] not in ("checking", "savings") or int(row["raw_amount_cents"]) >= 0:
        return None
    ctx = dict(row)
    ctx["abs_amount_cents"] = abs(int(row["raw_amount_cents"]))
    link = conn.execute(
        "SELECT card_account_id, competence_month FROM bill_payment_links WHERE payment_transaction_id = ?",
        (payment_tx_id,),
    ).fetchone()
    ctx["existing_link"] = dict(link) if link else None
    return ctx


def compute_import_preview_reconciliation(
    conn: sqlite3.Connection,
    *,
    payment_tx: dict[str, Any],
    card_account_id: int,
    competence_month: str,
    preview_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    payment_cents = abs(int(payment_tx["raw_amount_cents"]))
    existing_bill_cents, existing_item_count = compute_card_bill_net_cents(
        conn, card_account_id, competence_month
    )
    new_net = 0
    new_count = 0
    for r in preview_rows:
        if r.get("is_duplicate") or r["kind"] not in ("expense", "income"):
            continue
        amt = abs(int(r["raw_amount_cents"]))
        new_net += amt if r["kind"] == "expense" else -amt
        new_count += 1
    other_paid, _ = _linked_paid(
        conn, card_account_id, competence_month, exclude_tx_id=int(payment_tx["id"])
    )
    projected_bill = existing_bill_cents + new_net
    projected_paid = other_paid + payment_cents
    diff = projected_paid - projected_bill
    return {
        "payment_cents": payment_cents,
        "existing_bill_cents": existing_bill_cents,
        "existing_item_count": existing_item_count,
        "preview_new_net_cents": new_net,
        "preview_new_count": new_count,
        "other_linked_paid_cents": other_paid,
        "projected_bill_cents": projected_bill,
        "projected_paid_cents": projected_paid,
        "diff_cents": diff,
        "abs_diff_cents": abs(diff),
        "status": "matched" if diff == 0 else "diff",
    }
