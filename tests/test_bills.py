from __future__ import annotations

from pathlib import Path

import pytest

from app.db import db_session, init_db
from app.services.bills import (
    compute_card_bill_net_cents,
    get_bill_reconciliation,
    link_payment_to_bill,
    reconcile_links_after_card_changes,
    unlink_payment_from_bill,
)
from app.services.csv_importer import (
    commit_csv_import,
    delete_import_batch,
    delete_import_batch_with_details,
    preview_csv_import,
)
from app.services.finance import compute_account_balances, get_dashboard_summary


def _setup_accounts(conn) -> tuple[int, int, int]:
    bank_id = conn.execute("INSERT INTO banks (name) VALUES ('Itaú')").lastrowid
    chk_id = conn.execute(
        """
        INSERT INTO accounts (bank_id, name, account_type, initial_balance_cents, initial_balance_date)
        VALUES (?, 'Conta Corrente', 'checking', 500000, '2026-10-31')
        """,
        (bank_id,),
    ).lastrowid
    card_id = conn.execute(
        "INSERT INTO accounts (bank_id, name, account_type) VALUES (?, 'Cartão Black', 'credit_card')",
        (bank_id,),
    ).lastrowid
    return int(bank_id), int(chk_id), int(card_id)


def _insert_tx(
    conn,
    *,
    account_id: int,
    raw_date: str,
    desc: str,
    amount_cents: int,
    kind: str,
    competence_month: str | None = None,
    category_id: int | None = None,
    dedup_suffix: str = "",
) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO transactions (
                account_id, raw_date, raw_description, raw_amount_cents,
                dedup_hash, competence_month, display_name, category_id, kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                raw_date,
                desc,
                amount_cents,
                f"hash-{account_id}-{raw_date}-{desc}-{amount_cents}-{dedup_suffix}",
                competence_month or raw_date[:7],
                desc,
                category_id,
                kind,
            ),
        ).lastrowid
    )


def test_link_reconciliation_refunds_and_double_counting(tmp_path: Path):
    db_path = tmp_path / "bills.db"
    init_db(db_path)

    with db_session(db_path) as conn:
        _, chk_id, card_id = _setup_accounts(conn)
        cat_other = conn.execute("SELECT id FROM categories WHERE name = 'Outros'").fetchone()["id"]

        # Checking has a bill payment initially classified as expense with a category
        pay_id = _insert_tx(
            conn,
            account_id=chk_id,
            raw_date="2026-11-10",
            desc="PAGTO FATURA CARTAO",
            amount_cents=-95000,
            kind="expense",
            category_id=cat_other,
        )
        # Card has two expenses (1000.00 + 200.00), one refund (-250.00), and one internal payment received (transfer)
        _insert_tx(conn, account_id=card_id, raw_date="2026-11-02", desc="SUPERMERCADO", amount_cents=-100000, kind="expense")
        _insert_tx(conn, account_id=card_id, raw_date="2026-11-03", desc="FARMACIA", amount_cents=-20000, kind="expense")
        _insert_tx(conn, account_id=card_id, raw_date="2026-11-05", desc="ESTORNO LOJA", amount_cents=25000, kind="income")
        _insert_tx(conn, account_id=card_id, raw_date="2026-11-10", desc="PAGAMENTO RECEBIDO", amount_cents=95000, kind="transfer")

        bill_cents, item_count = compute_card_bill_net_cents(conn, card_id, "2026-11")
        assert bill_cents == 95000  # 1000 + 200 - 250
        assert item_count == 3  # transfer ignored

        recon = link_payment_to_bill(conn, pay_id, card_id, "2026-11")
        assert recon["status"] == "matched"
        assert recon["diff_cents"] == 0

        pay_row = conn.execute("SELECT kind, category_id FROM transactions WHERE id = ?", (pay_id,)).fetchone()
        assert pay_row["kind"] == "transfer"
        assert pay_row["category_id"] == cat_other  # category preserved

        # Dashboard avoids double counting; checking balance still includes outflow; card balance reflects net bill
        dash = get_dashboard_summary(conn, "2026-11")
        assert dash["expense_cents"] == 120000
        assert dash["income_cents"] == 25000
        assert dash["transfer_cents"] == 190000  # 950 checking + 950 card internal

        balances = compute_account_balances(conn, "2026-11")
        chk_bal = next(b for b in balances if b["id"] == chk_id)
        cc_bal = next(b for b in balances if b["id"] == card_id)
        assert chk_bal["balance_cents"] == 500000 - 95000
        assert cc_bal["bill_cents"] == 95000

        # Unlinking reverts payment back to expense and preserves category
        assert unlink_payment_from_bill(conn, pay_id, revert_to_expense=True) is True
        pay_row_after = conn.execute("SELECT kind, category_id FROM transactions WHERE id = ?", (pay_id,)).fetchone()
        assert pay_row_after["kind"] == "expense"
        assert pay_row_after["category_id"] == cat_other


def test_multiple_payments_and_mismatch(tmp_path: Path):
    db_path = tmp_path / "multi_pay.db"
    init_db(db_path)

    with db_session(db_path) as conn:
        _, chk_id, card_id = _setup_accounts(conn)
        _insert_tx(conn, account_id=card_id, raw_date="2026-11-04", desc="COMPRA", amount_cents=-100000, kind="expense")
        p1 = _insert_tx(conn, account_id=chk_id, raw_date="2026-11-08", desc="ADIANTAMENTO", amount_cents=-40000, kind="expense")
        p2 = _insert_tx(conn, account_id=chk_id, raw_date="2026-11-15", desc="PAGTO FINAL", amount_cents=-55000, kind="expense")

        r1 = link_payment_to_bill(conn, p1, card_id, "2026-11")
        assert r1["status"] == "diff"
        assert r1["diff_cents"] == -60000

        r2 = link_payment_to_bill(conn, p2, card_id, "2026-11")
        assert r2["payment_count"] == 2
        assert r2["paid_cents"] == 95000
        assert r2["diff_cents"] == -5000
        assert r2["abs_diff_cents"] == 5000
        assert r2["status"] == "diff"


def test_undo_card_batches_reverts_only_when_last_item_gone(tmp_path: Path):
    db_path = tmp_path / "undo_batches.db"
    init_db(db_path)

    with db_session(db_path) as conn:
        _, chk_id, card_id = _setup_accounts(conn)
        pay_id = _insert_tx(
            conn, account_id=chk_id, raw_date="2026-11-10", desc="FATURA", amount_cents=-30000, kind="expense"
        )

        cfg = {
            "delimiter": ",",
            "has_header": True,
            "date_column": "data",
            "description_column": "lançamento",
            "amount_column": "valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "positive",
        }
        csv1 = b"data,lan\xc3\xa7amento,valor\n2026-11-01,LOJA A,100.00\n"
        csv2 = b"data,lan\xc3\xa7amento,valor\n2026-11-02,LOJA B,200.00\n"

        p1 = preview_csv_import(conn, file_bytes=csv1, account_id=card_id, config=cfg, competence_month="2026-11")
        b1 = commit_csv_import(conn, account_id=card_id, profile_id=None, filename="b1.csv", competence_month="2026-11", rows=p1["rows"])["batch_id"]

        p2 = preview_csv_import(conn, file_bytes=csv2, account_id=card_id, config=cfg, competence_month="2026-11")
        b2 = commit_csv_import(conn, account_id=card_id, profile_id=None, filename="b2.csv", competence_month="2026-11", rows=p2["rows"])["batch_id"]

        recon = link_payment_to_bill(conn, pay_id, card_id, "2026-11")
        assert recon["status"] == "matched"

        # Undo first batch: second batch still has items -> link stays active
        d1 = delete_import_batch_with_details(conn, b1)
        assert d1 == {"removed_count": 1, "reverted_payments": 0}
        assert conn.execute("SELECT kind FROM transactions WHERE id = ?", (pay_id,)).fetchone()["kind"] == "transfer"
        assert get_bill_reconciliation(conn, card_id, "2026-11")["bill_cents"] == 20000

        # Undo second (last) batch -> link removed and payment reverts to expense
        removed2 = delete_import_batch(conn, b2)
        assert removed2 == 1
        assert conn.execute("SELECT kind FROM transactions WHERE id = ?", (pay_id,)).fetchone()["kind"] == "expense"
        assert conn.execute("SELECT COUNT(*) FROM bill_payment_links").fetchone()[0] == 0


def test_link_validation_errors(tmp_path: Path):
    db_path = tmp_path / "validation.db"
    init_db(db_path)

    with db_session(db_path) as conn:
        _, chk_id, card_id = _setup_accounts(conn)
        income_id = _insert_tx(conn, account_id=chk_id, raw_date="2026-11-05", desc="SALARIO", amount_cents=500000, kind="income")
        card_tx = _insert_tx(conn, account_id=card_id, raw_date="2026-11-05", desc="COMPRA", amount_cents=-5000, kind="expense")
        pay_id = _insert_tx(conn, account_id=chk_id, raw_date="2026-11-10", desc="FATURA", amount_cents=-5000, kind="expense")

        with pytest.raises(ValueError):
            link_payment_to_bill(conn, income_id, card_id, "2026-11")
        with pytest.raises(ValueError):
            link_payment_to_bill(conn, card_tx, card_id, "2026-11")
        with pytest.raises(ValueError):
            link_payment_to_bill(conn, pay_id, chk_id, "2026-11")
        with pytest.raises(ValueError):
            link_payment_to_bill(conn, pay_id, card_id, "2026/11")

        # Non-empty bill keeps links on reconcile_links_after_card_changes
        link_payment_to_bill(conn, pay_id, card_id, "2026-11")
        assert reconcile_links_after_card_changes(conn, card_id, "2026-11") == 0
