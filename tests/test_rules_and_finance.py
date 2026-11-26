from __future__ import annotations

from pathlib import Path

from app.db import db_session, init_db
from app.services.csv_importer import commit_csv_import, preview_csv_import
from app.services.finance import (
    compute_account_balances,
    get_dashboard_summary,
    get_lookahead,
    get_month_planning,
)
from app.services.rules import extract_installment, upsert_rule


def test_installment_extraction_and_rules(tmp_path: Path):
    assert extract_installment("AMAZON BR 02/06") == (2, 6, "AMAZON BR")
    assert extract_installment("LOJA XYZ PARC 3/12") == (3, 12, "LOJA XYZ")
    assert extract_installment("UBER *TRIP 1234") == (None, None, "UBER *TRIP 1234")
    # Invalid installment (total=1 or >48) should not match
    assert extract_installment("COMPRA 1/1") == (None, None, "COMPRA 1/1")


def test_balances_transfers_budgets_planning_and_installment_projection(tmp_path: Path):
    db_path = tmp_path / "finance.db"
    init_db(db_path)

    with db_session(db_path) as conn:
        bank_id = conn.execute("INSERT INTO banks (name) VALUES ('Nubank')").lastrowid
        checking_id = conn.execute(
            """
            INSERT INTO accounts (bank_id, name, account_type, initial_balance_cents, initial_balance_date)
            VALUES (?, 'NuConta', 'checking', 500000, '2026-10-31')
            """,
            (bank_id,),
        ).lastrowid
        card_id = conn.execute(
            """
            INSERT INTO accounts (bank_id, name, account_type)
            VALUES (?, 'Cartão Ultravioleta', 'credit_card')
            """,
            (bank_id,),
        ).lastrowid

        cat_food = conn.execute("SELECT id FROM categories WHERE name = 'Alimentação'").fetchone()["id"]
        cat_home = conn.execute("SELECT id FROM categories WHERE name = 'Moradia'").fetchone()["id"]
        conn.execute(
            "UPDATE categories SET monthly_budget_cents = 100000 WHERE id = ?",
            (cat_food,),
        )

        # Rule to classify bill payment on checking as transfer so it doesn't double-count
        upsert_rule(
            conn,
            pattern="PAGAMENTO FATURA",
            match_type="contains",
            target_display_name="Pagamento Fatura Cartão",
            target_category_id=None,
            target_kind="transfer",
            apply_existing=False,
        )
        upsert_rule(
            conn,
            pattern="IFOOD",
            match_type="contains",
            target_display_name="iFood",
            target_category_id=cat_food,
            target_kind="expense",
            apply_existing=False,
        )

        # Import checking account transactions for Nov 2026
        chk_csv = (
            "01/11/2026;SALARIO;10000,00\n"
            "05/11/2026;ALUGUEL;-2500,00\n"
            "10/11/2026;PAGAMENTO FATURA CARTAO;-1200,00\n"
        ).encode("utf-8")
        chk_cfg = {
            "delimiter": ";",
            "has_header": False,
            "date_column": "0",
            "description_column": "1",
            "amount_column": "2",
            "date_format": "%d/%m/%Y",
            "decimal_separator": ",",
            "expense_sign": "negative",
        }
        p1 = preview_csv_import(conn, file_bytes=chk_csv, account_id=checking_id, config=chk_cfg)
        commit_csv_import(conn, account_id=checking_id, profile_id=None, filename="chk.csv", competence_month=None, rows=p1["rows"])

        # Import credit card transactions for Nov 2026 (with an installment 02/04!)
        cc_csv = (
            "data,lançamento,valor\n"
            "2026-11-04,IFOOD *RESTAURANTE,850.00\n"
            "2026-10-12,NOTEBOOK STORE 02/04,350.00\n"
        ).encode("utf-8")
        cc_cfg = {
            "delimiter": ",",
            "has_header": True,
            "date_column": "data",
            "description_column": "lançamento",
            "amount_column": "valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "positive",
        }
        p2 = preview_csv_import(conn, file_bytes=cc_csv, account_id=card_id, config=cc_cfg, competence_month="2026-11")
        commit_csv_import(conn, account_id=card_id, profile_id=None, filename="cc.csv", competence_month="2026-11", rows=p2["rows"])

        # Add recurring items: Salary (already matched), Aluguel (already matched), Internet (still pending!)
        conn.execute(
            """
            INSERT INTO recurring_items (name, kind, expected_amount_cents, day_of_month, account_id, category_id, match_keyword)
            VALUES
                ('Salário', 'income', 1000000, 1, ?, NULL, 'SALARIO'),
                ('Aluguel', 'expense', 250000, 5, ?, ?, 'ALUGUEL'),
                ('Internet Fibra', 'expense', 15000, 20, ?, ?, 'VIVO FIBRA')
            """,
            (checking_id, checking_id, cat_home, checking_id, cat_home),
        )

        # Verify combined dashboard totals (NO double counting of the R$ 1.200 card bill payment!)
        dash = get_dashboard_summary(conn, "2026-11")
        assert dash["income_cents"] == 1000000
        # Expenses = 2500 (Aluguel) + 850 (iFood) + 350 (Notebook 02/04) = 3700.00
        assert dash["expense_cents"] == 370000
        assert dash["transfer_cents"] == 120000

        # Verify checking account balance INCLUDES the transfer outflow: 5000 + 10000 - 2500 - 1200 = 11300.00
        balances = compute_account_balances(conn, "2026-11")
        chk_bal = next(a for a in balances if a["id"] == checking_id)
        cc_bal = next(a for a in balances if a["id"] == card_id)
        assert chk_bal["balance_cents"] == 1130000
        assert cc_bal["bill_cents"] == 120000

        # Verify budget progress for Alimentação (850 / 1000 = 85%, status='warn')
        food_budget = next(b for b in dash["budgets"] if b["name"] == "Alimentação")
        assert food_budget["spent_cents"] == 85000
        assert food_budget["pct"] == 85.0
        assert food_budget["status"] == "warn"

        # Verify Nov planning: Aluguel & Salário auto-matched, Internet (150) pending
        nov_plan = get_month_planning(conn, "2026-11")
        assert nov_plan["expected_income_cents"] == 1000000
        assert nov_plan["actual_expense_cents"] == 370000
        assert nov_plan["pending_recurring_expense_cents"] == 15000
        assert nov_plan["total_committed_cents"] == 385000
        assert nov_plan["available_cents"] == 615000

        # Verify Dec 2026 lookahead projects installment 03/04 (350) + Jan 2027 projects 04/04 (350), Feb 2027 has 0!
        # DD/MM-like text is NOT inferred as an installment: nothing is projected automatically
        lookahead = get_lookahead(conn, "2026-11", months=4)
        assert all(len(m["projected_installments"]) == 0 for m in lookahead)

        # Explicitly registered installments (future card operations) still project
        conn.execute(
            """
            UPDATE transactions
            SET installment_current = 2, installment_total = 4, installment_group_key = 'notebook store'
            WHERE raw_description = 'NOTEBOOK STORE 02/04'
            """
        )
        # Installment fields on a non-credit-card account must be ignored
        conn.execute(
            """
            UPDATE transactions
            SET installment_current = 1, installment_total = 3, installment_group_key = 'aluguel'
            WHERE raw_description = 'ALUGUEL'
            """
        )
        lookahead = get_lookahead(conn, "2026-11", months=4)
        dec_plan = lookahead[1]
        jan_plan = lookahead[2]
        feb_plan = lookahead[3]
        assert len(dec_plan["projected_installments"]) == 1
        assert dec_plan["projected_installments"][0]["installment_label"] == "03/04"
        assert dec_plan["projected_installments_cents"] == 35000
        assert len(jan_plan["projected_installments"]) == 1
        assert jan_plan["projected_installments"][0]["installment_label"] == "04/04"
        assert len(feb_plan["projected_installments"]) == 0


def test_balance_anchor_traceback_and_forward_roll(tmp_path: Path):
    db_path = tmp_path / "anchor.db"
    init_db(db_path)

    with db_session(db_path) as conn:
        bank_id = conn.execute("INSERT INTO banks (name) VALUES ('Inter')").lastrowid
        acc_id = conn.execute(
            """
            INSERT INTO accounts (bank_id, name, account_type, initial_balance_cents, initial_balance_date)
            VALUES (?, 'Conta', 'checking', 150000, '2026-11-25')
            """,
            (bank_id,),
        ).lastrowid

        txs = [
            ("2026-09-15", -50000, "expense"),
            ("2026-10-05", 500000, "income"),
            ("2026-10-20", -200000, "expense"),
            ("2026-11-05", 500000, "income"),
            ("2026-11-10", -100000, "transfer"),
            ("2026-11-25", -5000, "expense"),
            ("2026-11-28", -15000, "expense"),
            ("2026-12-05", 500000, "income"),
        ]
        for i, (d, amt, kind) in enumerate(txs):
            conn.execute(
                """
                INSERT INTO transactions (account_id, raw_date, raw_description, raw_amount_cents,
                                          dedup_hash, competence_month, display_name, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (acc_id, d, f"TX{i}", amt, f"h{i}", d[:7], f"TX{i}", kind),
            )

        def bal(month: str) -> int:
            rows = compute_account_balances(conn, month)
            return next(a for a in rows if a["id"] == acc_id)["balance_cents"]

        assert bal("2026-08") == -495000
        assert bal("2026-09") == -545000
        assert bal("2026-10") == -245000
        assert bal("2026-11") == 135000
        assert bal("2026-12") == 635000

        # Without an anchor date, balance is initial + cumulative sum up to month end
        conn.execute("UPDATE accounts SET initial_balance_date = NULL WHERE id = ?", (acc_id,))
        assert bal("2026-10") == 150000 - 50000 + 500000 - 200000
