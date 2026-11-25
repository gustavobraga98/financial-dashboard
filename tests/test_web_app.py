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

    # Planning page for Dec 2026 shows projected installment 03/05 (R$ 300,00)
    plan_dec = client.get("/planejamento?month=2026-12")
    assert plan_dec.status_code == 200
    assert "03/05" in plan_dec.text
    assert "LOJA TECH" in plan_dec.text

    # Settings tabs all render cleanly
    for tab in ["accounts", "categories", "rules", "profiles"]:
        r = client.get(f"/configuracoes?tab={tab}")
        assert r.status_code == 200
    assert "Nubank Fatura Custom" in client.get("/configuracoes?tab=profiles").text
