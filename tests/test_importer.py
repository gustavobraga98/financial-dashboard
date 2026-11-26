from __future__ import annotations

from pathlib import Path

from app.db import db_session, init_db
from app.services.csv_importer import (
    commit_csv_import,
    delete_import_batch,
    inspect_csv,
    preview_csv_import,
)
from app.services.rules import upsert_rule


def _seed_bank_and_accounts(db_path: Path) -> tuple[int, int, int]:
    init_db(db_path)
    with db_session(db_path) as conn:
        bank_id = conn.execute("INSERT INTO banks (name, color) VALUES ('Itaú', '#EC7000')").lastrowid
        checking_id = conn.execute(
            """
            INSERT INTO accounts (bank_id, name, account_type, initial_balance_cents, initial_balance_date)
            VALUES (?, 'Conta Corrente', 'checking', 100000, '2026-11-01')
            """,
            (bank_id,),
        ).lastrowid
        card_id = conn.execute(
            """
            INSERT INTO accounts (bank_id, name, account_type)
            VALUES (?, 'Cartão Black', 'credit_card')
            """,
            (bank_id,),
        ).lastrowid
    return int(bank_id), int(checking_id), int(card_id)


def test_credit_csv_import_installments_dedup_and_billing_month(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _, _, card_id = _seed_bank_and_accounts(db_path)

    credit_csv = (
        "data,lançamento,valor\n"
        "2026-09-14,AMAZON BR 03/06,250.00\n"
        "2026-11-05,PADARIA CENTRAL,15.50\n"
        "2026-11-05,PADARIA CENTRAL,15.50\n"
        "2026-11-10,PAGAMENTO RECEBIDO,-1500.00\n"
    ).encode("utf-8")

    with db_session(db_path) as conn:
        cat_id = conn.execute("SELECT id FROM categories WHERE name = 'Compras'").fetchone()["id"]
        upsert_rule(
            conn,
            pattern="AMAZON BR",
            match_type="contains",
            target_display_name="Amazon",
            target_category_id=cat_id,
            target_kind="expense",
            apply_existing=False,
        )

        config = {
            "delimiter": ",",
            "has_header": True,
            "encoding": "utf-8-sig",
            "date_column": "data",
            "description_column": "lançamento",
            "amount_column": "valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "positive",
        }
        preview = preview_csv_import(
            conn,
            file_bytes=credit_csv,
            account_id=card_id,
            config=config,
            competence_month="2026-11",
        )

        assert preview["errors"] == []
        assert preview["new_count"] == 4
        assert preview["duplicate_count"] == 0

        # Check installment parsing + rule matching + competence month override
        amazon = preview["rows"][0]
        assert amazon["raw_date"] == "2026-09-14"
        assert amazon["competence_month"] == "2026-11"
        assert amazon["raw_description"] == "AMAZON BR 03/06"
        assert amazon["display_name"] == "Amazon"
        assert amazon["installment_current"] is None
        assert amazon["installment_total"] is None
        assert amazon["raw_amount_cents"] == -25000
        assert amazon["kind"] == "expense"

        # Two identical coffees on the same day must BOTH be treated as new (occurrence index 1 and 2)
        assert preview["rows"][1]["dedup_hash"] != preview["rows"][2]["dedup_hash"]

        # Bill payment credit on card should default to transfer (avoiding fake income)
        assert preview["rows"][3]["kind"] == "transfer"
        assert preview["rows"][3]["raw_amount_cents"] == 150000

        res = commit_csv_import(
            conn,
            account_id=card_id,
            profile_id=None,
            filename="fatura_nov.csv",
            competence_month="2026-11",
            rows=preview["rows"],
        )
        assert res["imported_count"] == 4

        # Re-importing the exact same CSV should mark all 4 as duplicates
        preview2 = preview_csv_import(
            conn,
            file_bytes=credit_csv,
            account_id=card_id,
            config=config,
            competence_month="2026-11",
        )
        assert preview2["new_count"] == 0
        assert preview2["duplicate_count"] == 4

        # Undo batch removes all 4 rows cleanly
        deleted = delete_import_batch(conn, res["batch_id"])
        assert deleted == 4
        remaining = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert remaining == 0


def test_semicolon_checking_statement_inspection_and_import(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _, checking_id, _ = _seed_bank_and_accounts(db_path)

    debit_txt = (
        "01/11/2026;SALARIO EMPRESA;8500,00\n"
        "05/11/2026;ALUGUEL APTO;-2200,50\n"
        "10/11/2026;PAGTO FATURA CARTAO;-1500,00\n"
    ).encode("latin-1")

    inspected = inspect_csv(debit_txt)
    assert inspected["delimiter"] == ";"
    assert inspected["has_header"] is False
    assert inspected["suggested"]["date_format"] == "%d/%m/%Y"
    assert inspected["suggested"]["decimal_separator"] == ","

    with db_session(db_path) as conn:
        config = {
            "delimiter": ";",
            "has_header": False,
            "encoding": "latin-1",
            "date_column": "0",
            "description_column": "1",
            "amount_column": "2",
            "date_format": "%d/%m/%Y",
            "decimal_separator": ",",
            "expense_sign": "negative",
        }
        preview = preview_csv_import(
            conn,
            file_bytes=debit_txt,
            account_id=checking_id,
            config=config,
        )
        assert preview["new_count"] == 3
        assert preview["rows"][0]["raw_amount_cents"] == 850000
        assert preview["rows"][0]["kind"] == "income"
        assert preview["rows"][1]["raw_amount_cents"] == -220050
        assert preview["rows"][1]["kind"] == "expense"
        assert preview["rows"][1]["competence_month"] == "2026-11"


def _build_xlsx() -> bytes:
    import io
    from datetime import date

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "Resumo"
    ws = wb.create_sheet("Extrato")
    ws.append(["Extrato Itaú"])
    ws.append(["Ag 0001", "CC 12345"])
    ws.append(["Data", "Lançamento", "Valor", "Obs"])
    ws.append([date(2026, 11, 1), "SALARIO EMPRESA", 8500.0, None])
    ws.append([date(2026, 11, 5), "ALUGUEL APTO", -2200.5, None])
    ws.append([date(2026, 11, 10), "PAGTO FATURA CARTAO", -1500.0, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_inspection_banner_skip_multisheet_and_import(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _, checking_id, _ = _seed_bank_and_accounts(db_path)
    xlsx_bytes = _build_xlsx()

    inspected = inspect_csv(xlsx_bytes, filename="extrato.xlsx")
    assert inspected["file_format"] == "xlsx"
    assert inspected["sheet_name"] == "Extrato"
    assert inspected["sheet_names"] == ["Resumo", "Extrato"]
    sugg = inspected["suggested"]
    assert sugg["skip_rows"] == 2
    assert sugg["date_column"] == "Data"
    assert sugg["description_column"] == "Lançamento"
    assert sugg["amount_column"] == "Valor"
    assert sugg["decimal_separator"] == "."

    config = {
        "has_header": True,
        "date_column": sugg["date_column"],
        "description_column": sugg["description_column"],
        "amount_column": sugg["amount_column"],
        "date_format": sugg["date_format"],
        "decimal_separator": sugg["decimal_separator"],
        "expense_sign": "negative",
        "skip_rows": sugg["skip_rows"],
        "sheet_name": inspected["sheet_name"],
    }
    with db_session(db_path) as conn:
        preview = preview_csv_import(
            conn, file_bytes=xlsx_bytes, account_id=checking_id, config=config, filename="extrato.xlsx"
        )
        assert preview["errors"] == []
        assert [r["raw_amount_cents"] for r in preview["rows"]] == [850000, -220050, -150000]
        assert [r["raw_date"] for r in preview["rows"]] == ["2026-11-01", "2026-11-05", "2026-11-10"]
        commit_csv_import(
            conn,
            account_id=checking_id,
            profile_id=None,
            filename="extrato.xlsx",
            competence_month=None,
            rows=preview["rows"],
        )
        again = preview_csv_import(
            conn, file_bytes=xlsx_bytes, account_id=checking_id, config=config, filename="extrato.xlsx"
        )
        assert again["duplicate_count"] == 3


def test_file_format_detection_and_text_xls_fallback():
    from app.services.csv_importer import detect_file_format

    assert detect_file_format(b"PK\x03\x04rest") == "xlsx"
    assert detect_file_format(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest") == "xls"
    assert detect_file_format(b"01/11/2026;SALARIO;10,00\n", "extrato.xls") == "csv"


def test_dd_mm_in_description_is_not_inferred_as_installment(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _, checking_id, _ = _seed_bank_and_accounts(db_path)
    csv_bytes = b"05/11/2026;PIX ENVIADO 05/11;-100,00\n"
    config = {
        "delimiter": ";",
        "has_header": False,
        "date_column": "0",
        "description_column": "1",
        "amount_column": "2",
        "date_format": "%d/%m/%Y",
        "decimal_separator": ",",
        "expense_sign": "negative",
    }
    with db_session(db_path) as conn:
        preview = preview_csv_import(conn, file_bytes=csv_bytes, account_id=checking_id, config=config)
        row = preview["rows"][0]
        assert row["display_name"] == "PIX ENVIADO 05/11"
        assert row["installment_current"] is None
        assert row["installment_total"] is None
        assert row["installment_group_key"] is None
