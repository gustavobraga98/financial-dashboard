from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import db_session
from app.services.csv_importer import (
    commit_csv_import,
    delete_import_batch,
    inspect_csv,
    preview_csv_import,
)
from app.web import load_common_data, parse_optional_int, templates

router = APIRouter(prefix="/importar")

# Lightweight in-memory staging cache for CSV previews (local single-user app)
_STAGED_UPLOADS: dict[str, dict[str, Any]] = {}
_MAX_STAGED = 20


def _stage_file(filename: str, content: bytes) -> str:
    if len(_STAGED_UPLOADS) >= _MAX_STAGED:
        oldest_key = next(iter(_STAGED_UPLOADS))
        _STAGED_UPLOADS.pop(oldest_key, None)
    token = uuid.uuid4().hex[:16]
    _STAGED_UPLOADS[token] = {"filename": filename, "content": content}
    return token


def _load_import_context(conn) -> dict[str, Any]:
    common = load_common_data(conn)
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
    batches = [
        dict(r)
        for r in conn.execute(
            """
            SELECT ib.*, a.name AS account_name, a.account_type, b.name AS bank_name
            FROM import_batches ib
            JOIN accounts a ON a.id = ib.account_id
            JOIN banks b ON b.id = a.bank_id
            ORDER BY ib.imported_at DESC, ib.id DESC
            LIMIT 25
            """
        ).fetchall()
    ]
    return {**common, "profiles": profiles, "batches": batches}


@router.get("", response_class=HTMLResponse)
def import_page(request: Request, msg: str | None = Query(default=None), error: str | None = Query(default=None)):
    with db_session() as conn:
        ctx = _load_import_context(conn)
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "active_nav": "import",
            "flash_msg": msg,
            "error_msg": error,
            "preview": None,
            **ctx,
        },
    )


@router.post("/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    account_id: int = Form(...),
    profile_id: str = Form(default="auto"),
    competence_month: str = Form(default=""),
    stage_token: str = Form(default=""),
    csv_file: UploadFile | None = File(default=None),
    # Optional custom overrides when user adjusts mapping in preview
    custom_mapping: str | None = Form(default=None),
    delimiter: str = Form(default=","),
    has_header: str | None = Form(default=None),
    encoding: str = Form(default="utf-8-sig"),
    date_column: str = Form(default=""),
    description_column: str = Form(default=""),
    amount_column: str = Form(default=""),
    date_format: str = Form(default="%Y-%m-%d"),
    decimal_separator: str = Form(default="."),
    expense_sign: str = Form(default="negative"),
    skip_rows: int = Form(default=0),
):
    if csv_file is not None and csv_file.filename:
        file_bytes = await csv_file.read()
        filename = csv_file.filename
        token = _stage_file(filename, file_bytes)
    elif stage_token and stage_token in _STAGED_UPLOADS:
        staged = _STAGED_UPLOADS[stage_token]
        file_bytes = staged["content"]
        filename = staged["filename"]
        token = stage_token
    else:
        return RedirectResponse(
            url="/importar?error=" + quote("Selecione um arquivo CSV para pré-visualizar."),
            status_code=303,
        )

    inspection = inspect_csv(file_bytes)

    with db_session() as conn:
        ctx = _load_import_context(conn)
        account = next((a for a in ctx["accounts"] if a["id"] == account_id), None)
        if not account:
            return RedirectResponse(
                url="/importar?error=" + quote("Conta não encontrada."),
                status_code=303,
            )

        selected_profile_id = parse_optional_int(profile_id)
        if custom_mapping:
            config = {
                "delimiter": delimiter,
                "has_header": bool(has_header),
                "encoding": encoding,
                "date_column": date_column,
                "description_column": description_column,
                "amount_column": amount_column,
                "date_format": date_format,
                "decimal_separator": decimal_separator,
                "expense_sign": expense_sign,
                "skip_rows": skip_rows,
            }
        elif selected_profile_id is not None:
            prof = next((p for p in ctx["profiles"] if p["id"] == selected_profile_id), None)
            if not prof:
                return RedirectResponse(
                    url="/importar?error=" + quote("Perfil de importação não encontrado."),
                    status_code=303,
                )
            config = {
                "delimiter": prof["delimiter"],
                "has_header": bool(prof["has_header"]),
                "encoding": prof["encoding"],
                "date_column": prof["date_column"],
                "description_column": prof["description_column"],
                "amount_column": prof["amount_column"],
                "date_format": prof["date_format"],
                "decimal_separator": prof["decimal_separator"],
                "expense_sign": prof["expense_sign"],
                "skip_rows": prof["skip_rows"],
            }
        else:
            # Auto-detect from CSV + account type
            sugg = inspection["suggested"]
            default_sign = "positive" if account["account_type"] == "credit_card" else "negative"
            config = {
                "delimiter": inspection["delimiter"],
                "has_header": inspection["has_header"],
                "encoding": inspection["encoding"],
                "date_column": sugg.get("date_column", "0"),
                "description_column": sugg.get("description_column", "1"),
                "amount_column": sugg.get("amount_column", "2"),
                "date_format": sugg.get("date_format", "%d/%m/%Y"),
                "decimal_separator": sugg.get("decimal_separator", ","),
                "expense_sign": default_sign,
                "skip_rows": 0,
            }

        preview_error = None
        preview = None
        try:
            preview = preview_csv_import(
                conn,
                file_bytes=file_bytes,
                account_id=account_id,
                config=config,
                competence_month=competence_month.strip() or None,
            )
        except Exception as exc:
            preview_error = str(exc)

    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "active_nav": "import",
            "preview": preview,
            "preview_error": preview_error,
            "inspection": inspection,
            "config": config,
            "stage_token": token,
            "filename": filename,
            "selected_account_id": account_id,
            "selected_profile_id": selected_profile_id,
            "competence_month": (
                preview["suggested_competence_month"]
                if preview
                else competence_month.strip()
            ),
            **ctx,
        },
    )


@router.post("/commit")
async def import_commit(request: Request):
    form = await request.form()
    stage_token = str(form.get("stage_token", ""))
    if stage_token not in _STAGED_UPLOADS:
        return RedirectResponse(
            url="/importar?error=" + quote("Sessão de pré-visualização expirada. Envie o arquivo novamente."),
            status_code=303,
        )

    staged = _STAGED_UPLOADS[stage_token]
    account_id = int(str(form.get("account_id")))
    selected_profile_id = parse_optional_int(str(form.get("profile_id", "")))
    competence_month = str(form.get("competence_month", "")).strip() or None

    config = {
        "delimiter": str(form.get("delimiter", ",")),
        "has_header": bool(form.get("has_header")),
        "encoding": str(form.get("encoding", "utf-8-sig")),
        "date_column": str(form.get("date_column", "0")),
        "description_column": str(form.get("description_column", "1")),
        "amount_column": str(form.get("amount_column", "2")),
        "date_format": str(form.get("date_format", "%Y-%m-%d")),
        "decimal_separator": str(form.get("decimal_separator", ".")),
        "expense_sign": str(form.get("expense_sign", "negative")),
        "skip_rows": int(str(form.get("skip_rows", "0") or "0")),
    }

    selected_indices = {int(v) for v in form.getlist("selected_rows") if str(v).isdigit()}
    save_profile_name = str(form.get("save_profile_name", "")).strip()

    with db_session() as conn:
        if save_profile_name:
            existing_prof = conn.execute(
                "SELECT id FROM import_profiles WHERE name = ?",
                (save_profile_name,),
            ).fetchone()
            if existing_prof:
                selected_profile_id = int(existing_prof["id"])
                conn.execute(
                    """
                    UPDATE import_profiles
                    SET account_id = ?, delimiter = ?, has_header = ?, encoding = ?,
                        date_column = ?, description_column = ?, amount_column = ?,
                        date_format = ?, decimal_separator = ?, expense_sign = ?, skip_rows = ?
                    WHERE id = ?
                    """,
                    (
                        account_id,
                        config["delimiter"],
                        1 if config["has_header"] else 0,
                        config["encoding"],
                        config["date_column"],
                        config["description_column"],
                        config["amount_column"],
                        config["date_format"],
                        config["decimal_separator"],
                        config["expense_sign"],
                        config["skip_rows"],
                        selected_profile_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO import_profiles (
                        name, account_id, delimiter, has_header, encoding,
                        date_column, description_column, amount_column,
                        date_format, decimal_separator, expense_sign, skip_rows
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        save_profile_name,
                        account_id,
                        config["delimiter"],
                        1 if config["has_header"] else 0,
                        config["encoding"],
                        config["date_column"],
                        config["description_column"],
                        config["amount_column"],
                        config["date_format"],
                        config["decimal_separator"],
                        config["expense_sign"],
                        config["skip_rows"],
                    ),
                )
                selected_profile_id = int(cur.lastrowid)

        preview = preview_csv_import(
            conn,
            file_bytes=staged["content"],
            account_id=account_id,
            config=config,
            competence_month=competence_month,
        )
        result = commit_csv_import(
            conn,
            account_id=account_id,
            profile_id=selected_profile_id,
            filename=staged["filename"],
            competence_month=preview["suggested_competence_month"]
            if preview["account"]["account_type"] == "credit_card"
            else None,
            rows=preview["rows"],
            selected_indices=selected_indices,
        )

    _STAGED_UPLOADS.pop(stage_token, None)
    msg = f"Importados {result['imported_count']} lançamento(s)"
    if result["skipped_count"] > 0:
        msg += f" ({result['skipped_count']} ignorado(s))"
    target_month = preview["suggested_competence_month"]
    return RedirectResponse(
        url=f"/lancamentos?month={target_month}&account_id={account_id}&msg={quote(msg)}",
        status_code=303,
    )


@router.post("/batches/{batch_id}/delete")
def undo_import_batch(batch_id: int):
    with db_session() as conn:
        removed = delete_import_batch(conn, batch_id)
    msg = f"Importação desfeita ({removed} lançamento(s) removido(s))."
    return RedirectResponse(url=f"/importar?msg={quote(msg)}", status_code=303)
