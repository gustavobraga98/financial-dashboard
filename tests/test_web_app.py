from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import db_session, init_db
from app.main import create_app


def _make_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    db_path = tmp_path / "web_test.db"
    monkeypatch.setenv("FINANCES_DB_PATH", str(db_path))
    init_db(db_path)
    app = create_app()
    return TestClient(app), db_path


def test_full_end_to_end_user_journey(tmp_path: Path, monkeypatch):
    client, db_path = _make_client(tmp_path, monkeypatch)

    # 1. Empty state renders cleanly on all main pages
    for path in ["/", "/lancamentos", "/importar", "/planejamento", "/configuracoes"]:
        resp = client.get(path)
        assert resp.status_code == 200, f"Failed on {path}"

    # 2. Create two banks and accounts via settings
    resp = client.post("/configuracoes/banks", data={"name": "Itaú", "color": "#EC7000"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "Itaú" in resp.text

    resp = client.post("/configuracoes/banks", data={"name": "Nubank", "color": "#820AD1"}, follow_redirects=True)
    assert resp.status_code == 200

    with db_session(db_path) as conn:
        itau_id = conn.execute("SELECT id FROM banks WHERE name = 'Itaú'").fetchone()["id"]
        nubank_id = conn.execute("SELECT id FROM banks WHERE name = 'Nubank'").fetchone()["id"]
        cat_transp = conn.execute("SELECT id FROM categories WHERE name = 'Transporte'").fetchone()["id"]

    client.post(
        "/configuracoes/accounts",
        data={
            "bank_id": str(itau_id),
            "name": "Conta Corrente",
            "account_type": "checking",
            "initial_balance": "3000,00",
            "initial_balance_date": "2026-11-01",
        },
        follow_redirects=True,
    )
    client.post(
        "/configuracoes/accounts",
        data={
            "bank_id": str(nubank_id),
            "name": "Cartão Roxinho",
            "account_type": "credit_card",
        },
        follow_redirects=True,
    )

    # Set a monthly budget on Transporte
    client.post(
        f"/configuracoes/categories/{cat_transp}",
        data={"color": "#0891B2", "monthly_budget": "500,00"},
        follow_redirects=True,
    )

    with db_session(db_path) as conn:
        chk_id = conn.execute("SELECT id FROM accounts WHERE name = 'Conta Corrente'").fetchone()["id"]
        cc_id = conn.execute("SELECT id FROM accounts WHERE name = 'Cartão Roxinho'").fetchone()["id"]

    # 3. Preview and commit Credit Card CSV with auto-detection + save profile
    cc_csv = (
        "data,lançamento,valor\n"
        "2026-11-03,UBER *TRIP 1111,45.50\n"
        "2026-11-08,UBER *TRIP 2222,54.50\n"
        "2026-10-15,LOJA TECH 02/05,300.00\n"
    ).encode("utf-8")

    prev = client.post(
        "/importar/preview",
        data={"account_id": str(cc_id), "profile_id": "auto", "competence_month": "2026-11"},
        files={"csv_file": ("fatura_nu.csv", cc_csv, "text/csv")},
    )
    assert prev.status_code == 200
    assert "3 novo(s)" in prev.text
    assert "02/05" in prev.text

    token_match = re.search(r'name="stage_token" value="([^"]+)"', prev.text)
    assert token_match is not None
    stage_token = token_match.group(1)

    commit = client.post(
        "/importar/commit",
        data={
            "stage_token": stage_token,
            "account_id": str(cc_id),
            "competence_month": "2026-11",
            "delimiter": ",",
            "has_header": "1",
            "encoding": "utf-8-sig",
            "date_column": "data",
            "description_column": "lançamento",
            "amount_column": "valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "positive",
            "save_profile_name": "Nubank Fatura Custom",
            "selected_rows": ["0", "1", "2"],
        },
        follow_redirects=True,
    )
    assert commit.status_code == 200
    assert "Importados 3 lançamento(s)" in commit.text

    # Re-uploading the same CSV should show 3 duplicates and 0 new
    prev_dup = client.post(
        "/importar/preview",
        data={"account_id": str(cc_id), "profile_id": "auto", "competence_month": "2026-11"},
        files={"csv_file": ("fatura_nu.csv", cc_csv, "text/csv")},
    )
    assert prev_dup.status_code == 200
    assert "0 novo(s)" in prev_dup.text
    assert "3 duplicata(s)" in prev_dup.text

    # 4. Inline HTMX edit on UBER *TRIP 1111 -> rename to "Uber", assign Transporte, save rule & apply retroactively!
    with db_session(db_path) as conn:
        uber_tx_id = conn.execute(
            "SELECT id FROM transactions WHERE raw_description = 'UBER *TRIP 1111'"
        ).fetchone()["id"]

    edit_frag = client.get(f"/lancamentos/{uber_tx_id}/edit")
    assert edit_frag.status_code == 200
    assert "UBER *TRIP 1111" in edit_frag.text

    upd = client.post(
        f"/lancamentos/{uber_tx_id}",
        headers={"HX-Request": "true"},
        data={
            "display_name": "Uber",
            "category_id": str(cat_transp),
            "kind": "expense",
            "competence_month": "2026-11",
            "notes": "Corridas trabalho",
            "save_rule": "1",
            "rule_match_type": "contains",
            "rule_pattern": "UBER *TRIP",
            "apply_existing": "1",
        },
    )
    assert upd.status_code == 200
    # Both UBER rows updated -> HX-Refresh triggered!
    assert upd.headers.get("HX-Refresh") == "true"

    with db_session(db_path) as conn:
        ubers = conn.execute(
            "SELECT display_name, raw_description, category_id FROM transactions WHERE raw_description LIKE 'UBER%'"
        ).fetchall()
        assert len(ubers) == 2
        assert all(r["display_name"] == "Uber" and r["category_id"] == cat_transp for r in ubers)
        # Raw bank descriptions remain untouched for retro-validation!
        assert {r["raw_description"] for r in ubers} == {"UBER *TRIP 1111", "UBER *TRIP 2222"}

    # 5. Add recurring salary & fixed rent in planning, verify dashboard + 6-month lookahead
    client.post(
        "/planejamento/items",
        data={
            "name": "Salário",
            "kind": "income",
            "expected_amount": "8000,00",
            "day_of_month": "5",
            "account_id": str(chk_id),
            "return_month": "2026-11",
        },
        follow_redirects=True,
    )
    client.post(
        "/planejamento/items",
        data={
            "name": "Aluguel",
            "kind": "expense",
            "expected_amount": "2000,00",
            "day_of_month": "10",
            "account_id": str(chk_id),
            "return_month": "2026-11",
        },
        follow_redirects=True,
    )

    # Dashboard global vs per-bank views
    dash_all = client.get("/?month=2026-11")
    assert dash_all.status_code == 200
    assert "R$ 400,00" in dash_all.text  # 45.50 + 54.50 + 300.00
    assert "R$ 3.000,00" in dash_all.text  # Checking initial balance
    assert "Transporte" in dash_all.text
    assert "R$ 100,00" in dash_all.text  # Uber budget spent

    dash_itau = client.get(f"/?month=2026-11&bank_id={itau_id}")
    assert dash_itau.status_code == 200
    assert "Itaú" in dash_itau.text

    dash_nu = client.get(f"/?month=2026-11&bank_id={nubank_id}")
    assert dash_nu.status_code == 200
    assert "Nubank" in dash_nu.text

    # Planning page keeps the section but no longer infers installments from DD/MM text
    plan_dec = client.get("/planejamento?month=2026-12")
    assert plan_dec.status_code == 200
    assert "Parcelas de cartão projetadas em" in plan_dec.text
    assert "03/05" not in plan_dec.text

    # Settings tabs all render cleanly
    for tab in ["accounts", "categories", "rules", "profiles"]:
        r = client.get(f"/configuracoes?tab={tab}")
        assert r.status_code == 200
    assert "Nubank Fatura Custom" in client.get("/configuracoes?tab=profiles").text


def test_current_balance_anchor_ui_and_traceback(tmp_path: Path, monkeypatch):
    from app.formatting import today_iso

    client, db_path = _make_client(tmp_path, monkeypatch)
    client.post("/configuracoes/banks", data={"name": "Inter", "color": "#FF7A00"})

    page = client.get("/configuracoes?tab=accounts")
    assert "Saldo atual (R$)" in page.text
    assert f'value="{today_iso()}"' in page.text

    with db_session(db_path) as conn:
        bank_id = conn.execute("SELECT id FROM banks WHERE name = 'Inter'").fetchone()["id"]

    client.post(
        "/configuracoes/accounts",
        data={
            "bank_id": str(bank_id),
            "name": "Conta",
            "account_type": "checking",
            "initial_balance": "1500,00",
            "initial_balance_date": "2026-11-25",
        },
    )
    client.post(
        "/configuracoes/accounts",
        data={
            "bank_id": str(bank_id),
            "name": "Cartão",
            "account_type": "credit_card",
            "initial_balance": "999,00",
            "initial_balance_date": "2026-11-25",
        },
    )

    with db_session(db_path) as conn:
        chk_id = conn.execute("SELECT id FROM accounts WHERE name = 'Conta'").fetchone()["id"]
        card = conn.execute("SELECT * FROM accounts WHERE name = 'Cartão'").fetchone()
        assert card["initial_balance_cents"] == 0
        assert card["initial_balance_date"] is None
        for i, (d, amt, kind) in enumerate([("2026-11-05", 500000, "income"), ("2026-11-25", -5000, "expense")]):
            conn.execute(
                """
                INSERT INTO transactions (account_id, raw_date, raw_description, raw_amount_cents,
                                          dedup_hash, competence_month, display_name, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chk_id, d, f"TX{i}", amt, f"h{i}", d[:7], f"TX{i}", kind),
            )

    nov = client.get("/?month=2026-11")
    assert nov.status_code == 200
    assert "R$ 1.500,00" in nov.text
    octo = client.get("/?month=2026-10")
    assert "-R$ 3.450,00" in octo.text


def test_large_csv_import_over_1000_rows(tmp_path: Path, monkeypatch):
    from datetime import date, timedelta

    client, db_path = _make_client(tmp_path, monkeypatch)
    client.post("/configuracoes/banks", data={"name": "Inter", "color": "#FF7A00"})
    with db_session(db_path) as conn:
        bank_id = conn.execute("SELECT id FROM banks WHERE name = 'Inter'").fetchone()["id"]
    client.post(
        "/configuracoes/accounts",
        data={"bank_id": str(bank_id), "name": "Conta", "account_type": "checking"},
    )
    with db_session(db_path) as conn:
        acc_id = conn.execute("SELECT id FROM accounts WHERE name = 'Conta'").fetchone()["id"]

    n = 1200
    lines = []
    for i in range(n):
        d = date(2025, 1, 1) + timedelta(days=i % 365)
        lines.append(f"{d.strftime('%d/%m/%Y')};TX {i};-10,00")
    csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")

    cfg = {
        "delimiter": ";",
        "has_header": "",
        "encoding": "utf-8-sig",
        "date_column": "0",
        "description_column": "1",
        "amount_column": "2",
        "date_format": "%d/%m/%Y",
        "decimal_separator": ",",
        "expense_sign": "negative",
        "skip_rows": "0",
    }

    prev = client.post(
        "/importar/preview",
        data={"account_id": str(acc_id), "profile_id": "auto"},
        files={"csv_file": ("big.csv", csv_bytes, "text/csv")},
    )
    assert prev.status_code == 200
    assert f"{n} novo(s)" in prev.text
    assert 'name="selected_rows_csv"' in prev.text
    token = re.search(r'name="stage_token" value="([^"]+)"', prev.text).group(1)

    commit = client.post(
        "/importar/commit",
        data={
            "stage_token": token,
            "account_id": str(acc_id),
            **cfg,
            "selected_rows_csv": ",".join(str(i) for i in range(n)),
        },
        follow_redirects=True,
    )
    assert commit.status_code == 200
    assert f"Importados {n} lançamento(s)" in commit.text
    with db_session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == n

    # Legacy style: >1000 repeated selected_rows fields must not hit the Starlette field limit
    prev2 = client.post(
        "/importar/preview",
        data={"account_id": str(acc_id), "profile_id": "auto"},
        files={"csv_file": ("big.csv", csv_bytes, "text/csv")},
    )
    token2 = re.search(r'name="stage_token" value="([^"]+)"', prev2.text).group(1)
    commit2 = client.post(
        "/importar/commit",
        data={
            "stage_token": token2,
            "account_id": str(acc_id),
            **cfg,
            "selected_rows": [str(i) for i in range(1050)],
        },
        follow_redirects=True,
    )
    assert commit2.status_code == 200
    assert "Importados 1050 lançamento(s)" in commit2.text


def test_xlsx_upload_preview_and_commit_via_web(tmp_path: Path, monkeypatch):
    import io
    from datetime import date

    import openpyxl

    client, db_path = _make_client(tmp_path, monkeypatch)
    client.post("/configuracoes/banks", data={"name": "Inter", "color": "#FF7A00"})
    with db_session(db_path) as conn:
        bank_id = conn.execute("SELECT id FROM banks WHERE name = 'Inter'").fetchone()["id"]
    client.post(
        "/configuracoes/accounts",
        data={"bank_id": str(bank_id), "name": "Conta", "account_type": "checking"},
    )
    with db_session(db_path) as conn:
        acc_id = conn.execute("SELECT id FROM accounts WHERE name = 'Conta'").fetchone()["id"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extrato"
    ws.append(["Banco Inter - Extrato"])
    ws.append(["Data", "Descrição", "Valor"])
    ws.append([date(2026, 11, 3), "PADARIA", -15.5])
    ws.append([date(2026, 11, 4), "SALARIO", 3000.0])
    buf = io.BytesIO()
    wb.save(buf)

    prev = client.post(
        "/importar/preview",
        data={"account_id": str(acc_id), "profile_id": "auto"},
        files={
            "csv_file": (
                "extrato.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert prev.status_code == 200
    assert "2 novo(s)" in prev.text
    token = re.search(r'name="stage_token" value="([^"]+)"', prev.text).group(1)
    rows_csv = re.search(r'name="selected_rows_csv" id="selected_rows_csv" value="([^"]*)"', prev.text).group(1)

    commit = client.post(
        "/importar/commit",
        data={
            "stage_token": token,
            "account_id": str(acc_id),
            "delimiter": ",",
            "has_header": "1",
            "encoding": "xlsx",
            "date_column": "Data",
            "description_column": "Descrição",
            "amount_column": "Valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "negative",
            "skip_rows": "1",
            "sheet_name": "Extrato",
            "selected_rows_csv": rows_csv,
        },
        follow_redirects=True,
    )
    assert commit.status_code == 200
    assert "Importados 2 lançamento(s)" in commit.text
    with db_session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2


def test_bill_detail_after_payment_end_to_end(tmp_path: Path, monkeypatch):
    client, db_path = _make_client(tmp_path, monkeypatch)
    client.post("/configuracoes/banks", data={"name": "Itaú", "color": "#EC7000"})
    with db_session(db_path) as conn:
        bank_id = conn.execute("SELECT id FROM banks WHERE name = 'Itaú'").fetchone()["id"]
    client.post(
        "/configuracoes/accounts",
        data={
            "bank_id": str(bank_id),
            "name": "Conta Corrente",
            "account_type": "checking",
            "initial_balance": "5000,00",
            "initial_balance_date": "2026-11-01",
        },
    )
    with db_session(db_path) as conn:
        chk_id = conn.execute("SELECT id FROM accounts WHERE name = 'Conta Corrente'").fetchone()["id"]

    # 1. Import checking statement with a credit card bill payment (initially expense)
    chk_csv = "05/11/2026;SALARIO;8000,00\n10/11/2026;PAGAMENTO FATURA ITAU;-150,00\n".encode("utf-8")
    p_chk = client.post(
        "/importar/preview",
        data={"account_id": str(chk_id), "profile_id": "auto"},
        files={"csv_file": ("chk.csv", chk_csv, "text/csv")},
    )
    tok_chk = re.search(r'name="stage_token" value="([^"]+)"', p_chk.text).group(1)
    client.post(
        "/importar/commit",
        data={
            "stage_token": tok_chk,
            "account_id": str(chk_id),
            "delimiter": ";",
            "encoding": "utf-8-sig",
            "date_column": "0",
            "description_column": "1",
            "amount_column": "2",
            "date_format": "%d/%m/%Y",
            "decimal_separator": ",",
            "expense_sign": "negative",
            "selected_rows_csv": "0,1",
        },
        follow_redirects=True,
    )

    with db_session(db_path) as conn:
        pay_id = conn.execute(
            "SELECT id FROM transactions WHERE raw_description = 'PAGAMENTO FATURA ITAU'"
        ).fetchone()["id"]

    # 2. While still an expense, "Detalhar fatura" is hidden and /detalhar rejects it
    chk_before = client.get(f"/lancamentos?month=2026-11&account_id={chk_id}")
    assert "Detalhar fatura" not in chk_before.text
    assert client.get(f"/lancamentos/{pay_id}/detalhar").status_code == 400

    # Mark the payment as Transferência / Fatura -> button opens up
    marked = client.post(
        f"/lancamentos/{pay_id}",
        headers={"HX-Request": "true"},
        data={
            "display_name": "PAGAMENTO FATURA ITAU",
            "category_id": "",
            "kind": "transfer",
            "competence_month": "2026-11",
            "notes": "",
        },
    )
    assert marked.status_code == 200
    assert "Detalhar fatura" in marked.text

    # Open "Detalhar fatura" -> no cards exist yet -> create card inline
    panel = client.get(f"/lancamentos/{pay_id}/detalhar")
    assert panel.status_code == 200
    assert "Você ainda não tem nenhuma conta de cartão" in panel.text

    created = client.post(
        f"/lancamentos/{pay_id}/criar-cartao",
        data={"bank_id": str(bank_id), "name": "Itaucard Black"},
    )
    assert created.status_code == 200
    assert "Itaucard Black" in created.text
    assert "Subir CSV / Excel da fatura" in created.text

    with db_session(db_path) as conn:
        card_id = conn.execute("SELECT id FROM accounts WHERE name = 'Itaucard Black'").fetchone()["id"]

    # 3. Go to /importar?link_payment_id=... -> preview shows Bateu ✓ -> commit auto-links
    imp_page = client.get(
        f"/importar?link_payment_id={pay_id}&account_id={card_id}&competence_month=2026-11"
    )
    assert imp_page.status_code == 200
    assert "PAGAMENTO FATURA ITAU" in imp_page.text
    assert "R$ 150,00" in imp_page.text

    cc_csv = "data,lançamento,valor\n2026-11-02,MERCADO,100.00\n2026-11-03,PADARIA,50.00\n".encode("utf-8")
    p_cc = client.post(
        "/importar/preview",
        data={
            "account_id": str(card_id),
            "profile_id": "auto",
            "competence_month": "2026-11",
            "link_payment_id": str(pay_id),
        },
        files={"csv_file": ("fatura.csv", cc_csv, "text/csv")},
    )
    assert p_cc.status_code == 200
    assert "Bateu ✓" in p_cc.text

    tok_cc = re.search(r'name="stage_token" value="([^"]+)"', p_cc.text).group(1)
    c_cc = client.post(
        "/importar/commit",
        data={
            "stage_token": tok_cc,
            "account_id": str(card_id),
            "competence_month": "2026-11",
            "link_payment_id": str(pay_id),
            "delimiter": ",",
            "has_header": "1",
            "encoding": "utf-8-sig",
            "date_column": "data",
            "description_column": "lançamento",
            "amount_column": "valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "positive",
            "selected_rows_csv": "0,1",
        },
        follow_redirects=True,
    )
    assert c_cc.status_code == 200
    assert "Pagamento vinculado à fatura (Bateu ✓)" in c_cc.text
    assert "2 item(ns)" in c_cc.text

    # 4. Checking list shows clickable badge; dashboard has no double-counting (R$ 150,00, not R$ 300,00)
    chk_list = client.get(f"/lancamentos?month=2026-11&account_id={chk_id}")
    assert "Itaucard Black · 2 itens" in chk_list.text
    assert "Bateu ✓" in chk_list.text

    dash = client.get("/?month=2026-11")
    assert dash.status_code == 200
    with db_session(db_path) as conn:
        from app.services.finance import get_dashboard_summary
        summary = get_dashboard_summary(conn, "2026-11")
        assert summary["expense_cents"] == 15000
        assert summary["transfer_cents"] == 15000


def test_bill_link_before_payment_and_undo_revert(tmp_path: Path, monkeypatch):
    client, db_path = _make_client(tmp_path, monkeypatch)
    client.post("/configuracoes/banks", data={"name": "Nubank", "color": "#820AD1"})
    with db_session(db_path) as conn:
        bank_id = conn.execute("SELECT id FROM banks WHERE name = 'Nubank'").fetchone()["id"]
    client.post("/configuracoes/accounts", data={"bank_id": str(bank_id), "name": "NuConta", "account_type": "checking"})
    client.post("/configuracoes/accounts", data={"bank_id": str(bank_id), "name": "Roxinho", "account_type": "credit_card"})
    with db_session(db_path) as conn:
        chk_id = conn.execute("SELECT id FROM accounts WHERE name = 'NuConta'").fetchone()["id"]
        card_id = conn.execute("SELECT id FROM accounts WHERE name = 'Roxinho'").fetchone()["id"]

    # Import card bill first (R$ 200,00)
    cc_csv = "data,lançamento,valor\n2026-11-04,LOJA X,200.00\n".encode("utf-8")
    p_cc = client.post(
        "/importar/preview",
        data={"account_id": str(card_id), "profile_id": "auto", "competence_month": "2026-11"},
        files={"csv_file": ("nu.csv", cc_csv, "text/csv")},
    )
    tok_cc = re.search(r'name="stage_token" value="([^"]+)"', p_cc.text).group(1)
    client.post(
        "/importar/commit",
        data={
            "stage_token": tok_cc,
            "account_id": str(card_id),
            "competence_month": "2026-11",
            "delimiter": ",",
            "has_header": "1",
            "encoding": "utf-8-sig",
            "date_column": "data",
            "description_column": "lançamento",
            "amount_column": "valor",
            "date_format": "%Y-%m-%d",
            "decimal_separator": ".",
            "expense_sign": "positive",
            "selected_rows_csv": "0",
        },
        follow_redirects=True,
    )

    # Import checking payment later (R$ 200,00) already classified as transfer
    with db_session(db_path) as conn:
        batch_id = conn.execute("SELECT id FROM import_batches WHERE account_id = ?", (card_id,)).fetchone()["id"]
        pay_id = conn.execute(
            """
            INSERT INTO transactions (account_id, raw_date, raw_description, raw_amount_cents,
                                      dedup_hash, competence_month, display_name, kind)
            VALUES (?, '2026-11-10', 'PAGTO FATURA', -20000, 'hpay', '2026-11', 'PAGTO FATURA', 'transfer')
            """,
            (chk_id,),
        ).lastrowid

    # 1-click link via HTMX
    panel = client.get(f"/lancamentos/{pay_id}/detalhar")
    assert "Ou vincular a uma fatura já importada" in panel.text
    assert "Roxinho" in panel.text

    link_resp = client.post(
        f"/lancamentos/{pay_id}/vincular-fatura",
        headers={"HX-Request": "true"},
        data={"card_account_id": str(card_id), "competence_month": "2026-11"},
    )
    assert link_resp.status_code == 200
    assert link_resp.headers.get("HX-Refresh") == "true"
    assert "Bateu ✓" in link_resp.text

    # Undo card batch -> payment reverts to expense automatically
    undo = client.post(f"/importar/batches/{batch_id}/delete", follow_redirects=True)
    assert undo.status_code == 200
    assert "1 pagamento(s) de fatura voltaram para Despesa." in undo.text
    with db_session(db_path) as conn:
        assert conn.execute("SELECT kind FROM transactions WHERE id = ?", (pay_id,)).fetchone()["kind"] == "expense"

    # Re-import card item, re-link, then test manual unlink and manual kind change
    conn_test = db_session(db_path)
    with conn_test as conn:
        conn.execute(
            """
            INSERT INTO transactions (account_id, raw_date, raw_description, raw_amount_cents,
                                      dedup_hash, competence_month, display_name, kind)
            VALUES (?, '2026-11-04', 'LOJA Y', -20000, 'hy', '2026-11', 'LOJA Y', 'expense')
            """,
            (card_id,),
        )
    client.post(
        f"/lancamentos/{pay_id}/vincular-fatura",
        data={"card_account_id": str(card_id), "competence_month": "2026-11"},
    )
    unlink_resp = client.post(
        f"/lancamentos/{pay_id}/desvincular-fatura",
        headers={"HX-Request": "true"},
    )
    assert unlink_resp.status_code == 200
    assert unlink_resp.headers.get("HX-Refresh") == "true"
    with db_session(db_path) as conn:
        assert conn.execute("SELECT kind FROM transactions WHERE id = ?", (pay_id,)).fetchone()["kind"] == "expense"

    # Link again and manually switch kind to expense via edit -> link is cleaned up
    client.post(
        f"/lancamentos/{pay_id}/vincular-fatura",
        data={"card_account_id": str(card_id), "competence_month": "2026-11"},
    )
    client.post(
        f"/lancamentos/{pay_id}",
        headers={"HX-Request": "true"},
        data={
            "display_name": "PAGTO FATURA",
            "category_id": "",
            "kind": "expense",
            "competence_month": "2026-11",
            "notes": "",
        },
    )
    with db_session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM bill_payment_links").fetchone()[0] == 0
