from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from typing import Any

from app.formatting import current_month, parse_brl_to_cents
from app.services.rules import find_matching_rule, normalize_text

XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def detect_file_format(file_bytes: bytes, filename: str | None = None) -> str:
    if file_bytes.startswith(XLSX_MAGIC):
        return "xlsx"
    if file_bytes.startswith(XLS_MAGIC):
        return "xls"
    ext = filename.lower().rsplit(".", 1)[-1] if filename and "." in filename else ""
    if ext in ("xlsx", "xlsm"):
        return "xlsx"
    # Many banks export text files named .xls; without OLE2 magic treat as CSV.
    return "csv"


def _normalize_excel_cell(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{round(val, 6):.6f}".rstrip("0").rstrip(".")
    return str(val).strip()


def _trim_row(row: list[str]) -> list[str]:
    while row and row[-1] == "":
        row.pop()
    return row


def _read_spreadsheet_rows(
    file_bytes: bytes, file_format: str, sheet_name: str | None = None
) -> tuple[list[list[str]], list[str], str]:
    rows: list[list[str]] = []
    if file_format == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        try:
            sheet_names = list(wb.sheetnames)
            if not sheet_names:
                return [], [], ""
            chosen = sheet_name if sheet_name in sheet_names else None
            if chosen is None:
                for name in sheet_names:
                    ws_probe = wb[name]
                    found = False
                    for i, r in enumerate(ws_probe.iter_rows(values_only=True)):
                        if i >= 20:
                            break
                        if any(c not in (None, "") for c in r):
                            found = True
                            break
                    if found:
                        chosen = name
                        break
                if chosen is None:
                    chosen = sheet_names[0]
            ws = wb[chosen]
            for r in ws.iter_rows(values_only=True):
                str_row = _trim_row([_normalize_excel_cell(c) for c in r])
                if any(str_row):
                    rows.append(str_row)
            return rows, sheet_names, chosen
        finally:
            wb.close()

    import xlrd

    wb = xlrd.open_workbook(file_contents=file_bytes)
    sheet_names = list(wb.sheet_names())
    if not sheet_names:
        return [], [], ""
    chosen = sheet_name if sheet_name in sheet_names else None
    if chosen is None:
        chosen = next((n for n in sheet_names if wb.sheet_by_name(n).nrows > 0), sheet_names[0])
    sh = wb.sheet_by_name(chosen)
    for ridx in range(sh.nrows):
        out: list[str] = []
        for cell in sh.row(ridx):
            if cell.ctype == xlrd.XL_CELL_DATE:
                out.append(xlrd.xldate_as_datetime(cell.value, wb.datemode).strftime("%Y-%m-%d"))
            elif cell.ctype == xlrd.XL_CELL_EMPTY:
                out.append("")
            else:
                out.append(_normalize_excel_cell(cell.value))
        out = _trim_row(out)
        if any(out):
            rows.append(out)
    return rows, sheet_names, chosen


_DATE_KW = ("data", "date", "dt")
_DESC_KW = ("lancamento", "descricao", "historico", "estabelecimento", "title", "memo", "description")
_AMT_KW = ("valor", "amount", "quantia", "total", "credito", "debito")


def _detect_table_start(raw_rows: list[list[str]]) -> int:
    window = raw_rows[:25]
    for idx, row in enumerate(window):
        cells = [c for c in row if c.strip()]
        if len(cells) < 3:
            continue
        norm = [normalize_text(c) for c in cells]
        groups = sum(
            1
            for kws in (_DATE_KW, _DESC_KW, _AMT_KW)
            if any(any(k in n for k in kws) for n in norm)
        )
        if groups >= 2:
            return idx
    for idx, row in enumerate(window):
        cells = [c for c in row if c.strip()]
        if len(cells) < 3:
            continue
        date_ok = amt_ok = False
        for c in cells:
            if not date_ok:
                try:
                    parse_date_flexible(c)
                    date_ok = True
                    continue
                except ValueError:
                    pass
            if not amt_ok:
                try:
                    parse_brl_to_cents(c)
                    amt_ok = True
                except ValueError:
                    pass
        if date_ok and amt_ok:
            return idx
    return 0

DATE_FORMATS_TO_TRY = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
]

CREDIT_BILL_PAYMENT_HINTS = (
    "pagamento recebido",
    "pagamento efetuado",
    "pagamento de fatura",
    "pagamento fatura",
    "pagto fatura",
    "pag fatura",
)


def decode_csv_bytes(file_bytes: bytes, preferred_encoding: str = "utf-8-sig") -> tuple[str, str]:
    encodings = [preferred_encoding, "utf-8-sig", "utf-8", "cp1252", "latin-1"]
    seen: set[str] = set()
    for enc in encodings:
        if not enc or enc in seen:
            continue
        seen.add(enc)
        try:
            return file_bytes.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1", errors="replace"), "latin-1"


def detect_delimiter(sample_text: str) -> str:
    lines = [ln for ln in sample_text.splitlines() if ln.strip()][:10]
    if not lines:
        return ","
    candidates = [";", ",", "\t"]
    scores = {}
    for delim in candidates:
        counts = [ln.count(delim) for ln in lines]
        if max(counts) == 0:
            scores[delim] = 0
        else:
            # Prefer consistent non-zero delimiter counts across lines
            nonzero = [c for c in counts if c > 0]
            consistency = len(nonzero) / len(counts)
            scores[delim] = (sum(counts) / len(counts)) * consistency
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else ","


def parse_date_flexible(raw: str, preferred_format: str | None = None) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Data vazia")
    # Strip time portion if present (e.g. "2026-11-10 14:30:00")
    if " " in text and len(text.split(" ")[0]) >= 8:
        text = text.split(" ")[0]

    formats = []
    if preferred_format:
        formats.append(preferred_format)
    for fmt in DATE_FORMATS_TO_TRY:
        if fmt not in formats:
            formats.append(fmt)

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Formato de data não reconhecido: {raw!r}")


def _guess_date_format(samples: list[str]) -> str:
    for fmt in DATE_FORMATS_TO_TRY:
        ok = 0
        for s in samples:
            s_clean = s.strip().split(" ")[0]
            if not s_clean:
                continue
            try:
                datetime.strptime(s_clean, fmt)
                ok += 1
            except ValueError:
                pass
        if ok > 0 and ok >= max(1, len(samples) // 2):
            return fmt
    return "%d/%m/%Y"


def _guess_decimal_separator(samples: list[str]) -> str:
    comma_dec = 0
    dot_dec = 0
    for s in samples:
        t = s.strip().replace("R$", "").replace(" ", "")
        if "," in t and "." in t:
            if t.rfind(",") > t.rfind("."):
                comma_dec += 1
            else:
                dot_dec += 1
        elif "," in t:
            comma_dec += 1
        elif "." in t:
            dot_dec += 1
    return "," if comma_dec > dot_dec else "."


def inspect_csv(
    file_bytes: bytes,
    preferred_encoding: str = "utf-8-sig",
    filename: str | None = None,
    sheet_name: str | None = None,
    skip_rows: int | None = None,
) -> dict[str, Any]:
    file_format = detect_file_format(file_bytes, filename)
    sheet_names: list[str] = []
    chosen_sheet = ""
    if file_format in ("xlsx", "xls"):
        raw_rows, sheet_names, chosen_sheet = _read_spreadsheet_rows(
            file_bytes, file_format, sheet_name=sheet_name
        )
        used_encoding = file_format
        delimiter = ","
    else:
        text, used_encoding = decode_csv_bytes(file_bytes, preferred_encoding)
        delimiter = detect_delimiter(text)
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not raw_rows:
        return {
            "encoding": used_encoding,
            "delimiter": delimiter,
            "has_header": True,
            "columns": [],
            "sample_rows": [],
            "suggested": {},
            "file_format": file_format,
            "sheet_names": sheet_names,
            "sheet_name": chosen_sheet,
        }

    detected_skip = skip_rows if skip_rows is not None else _detect_table_start(raw_rows)
    effective_rows = raw_rows[detected_skip:] if detected_skip > 0 else raw_rows
    if not effective_rows:
        effective_rows = raw_rows
        detected_skip = 0

    first_row = effective_rows[0]
    # Heuristic: if first row contains a parseable date in col 0 or a monetary value, likely no header
    first_looks_like_data = False
    if first_row:
        try:
            parse_date_flexible(first_row[0])
            first_looks_like_data = True
        except ValueError:
            first_looks_like_data = False

    has_header = not first_looks_like_data
    if has_header:
        columns = [c.strip() for c in first_row]
        data_rows = effective_rows[1:8]
    else:
        columns = [str(i) for i in range(len(first_row))]
        data_rows = effective_rows[:7]

    # Suggest column mapping
    date_col = columns[0] if columns else ""
    desc_col = columns[1] if len(columns) > 1 else date_col
    amt_col = columns[2] if len(columns) > 2 else desc_col

    if has_header:
        for col in columns:
            low = normalize_text(col)
            if any(k in low for k in ("data", "date", "dt")):
                date_col = col
            elif any(k in low for k in ("lancamento", "descricao", "historico", "estabelecimento", "title", "memo", "description")):
                desc_col = col
            elif any(k in low for k in ("valor", "amount", "quantia", "total")):
                amt_col = col

    date_idx = columns.index(date_col) if date_col in columns else 0
    amt_idx = columns.index(amt_col) if amt_col in columns else min(2, len(columns) - 1)

    date_samples = [r[date_idx] for r in data_rows if len(r) > date_idx]
    amt_samples = [r[amt_idx] for r in data_rows if len(r) > amt_idx]

    return {
        "encoding": used_encoding,
        "delimiter": delimiter,
        "has_header": has_header,
        "columns": columns,
        "sample_rows": data_rows[:6],
        "suggested": {
            "date_column": date_col,
            "description_column": desc_col,
            "amount_column": amt_col,
            "date_format": _guess_date_format(date_samples),
            "decimal_separator": _guess_decimal_separator(amt_samples),
            "skip_rows": detected_skip,
            "sheet_name": chosen_sheet,
        },
        "file_format": file_format,
        "sheet_names": sheet_names,
        "sheet_name": chosen_sheet,
    }


def _resolve_col_index(col_spec: str, headers: list[str] | None) -> int:
    spec = str(col_spec).strip()
    if headers is not None:
        # Exact match first
        if spec in headers:
            return headers.index(spec)
        # Normalized case/accent-insensitive match
        spec_norm = normalize_text(spec)
        for idx, h in enumerate(headers):
            if normalize_text(h) == spec_norm:
                return idx
    if spec.isdigit():
        return int(spec)
    raise ValueError(f"Coluna {col_spec!r} não encontrada no arquivo CSV (colunas: {headers})")


def compute_dedup_hash(
    account_id: int,
    raw_date: str,
    raw_amount_cents: int,
    raw_description: str,
    occurrence_index: int,
) -> str:
    payload = f"{account_id}|{raw_date}|{raw_amount_cents}|{raw_description.strip()}|{occurrence_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def preview_csv_import(
    conn: sqlite3.Connection,
    *,
    file_bytes: bytes,
    account_id: int,
    config: dict[str, Any],
    competence_month: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    account = conn.execute(
        """
        SELECT a.*, b.name AS bank_name
        FROM accounts a
        JOIN banks b ON b.id = a.bank_id
        WHERE a.id = ?
        """,
        (account_id,),
    ).fetchone()
    if not account:
        raise ValueError("Conta selecionada não encontrada.")

    encoding = config.get("encoding") or "utf-8-sig"
    delimiter = config.get("delimiter") or ","
    if delimiter == "\\t":
        delimiter = "\t"
    has_header = bool(config.get("has_header", True))
    skip_rows = int(config.get("skip_rows") or 0)
    date_format = config.get("date_format") or "%Y-%m-%d"
    decimal_sep = config.get("decimal_separator") or "."
    expense_sign = config.get("expense_sign") or "negative"

    file_format = detect_file_format(file_bytes, filename)
    if file_format in ("xlsx", "xls"):
        all_rows, _, _ = _read_spreadsheet_rows(
            file_bytes, file_format, sheet_name=config.get("sheet_name") or None
        )
        used_encoding = file_format
    else:
        text, used_encoding = decode_csv_bytes(file_bytes, encoding)
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        all_rows = [row for row in reader if any(cell.strip() for cell in row)]
    if skip_rows > 0:
        all_rows = all_rows[skip_rows:]

    if not all_rows:
        return {
            "account": dict(account),
            "encoding": used_encoding,
            "rows": [],
            "errors": ["O arquivo CSV está vazio."],
            "new_count": 0,
            "duplicate_count": 0,
            "suggested_competence_month": competence_month or current_month(),
        }

    headers: list[str] | None = None
    data_rows = all_rows
    if has_header:
        headers = [c.strip() for c in all_rows[0]]
        data_rows = all_rows[1:]

    date_idx = _resolve_col_index(config["date_column"], headers)
    desc_idx = _resolve_col_index(config["description_column"], headers)
    amt_idx = _resolve_col_index(config["amount_column"], headers)

    categories_by_id = {
        r["id"]: dict(r)
        for r in conn.execute("SELECT id, name, color FROM categories").fetchall()
    }
    existing_hashes = {
        r["dedup_hash"]
        for r in conn.execute(
            "SELECT dedup_hash FROM transactions WHERE account_id = ?",
            (account_id,),
        ).fetchall()
    }

    parsed_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    occurrence_counter: Counter[tuple[str, int, str]] = Counter()
    observed_months: list[str] = []

    for row_num, row in enumerate(data_rows, start=1):
        try:
            max_idx = max(date_idx, desc_idx, amt_idx)
            if len(row) <= max_idx:
                raise ValueError(f"Linha {row_num} tem apenas {len(row)} coluna(s).")

            raw_date = parse_date_flexible(row[date_idx], date_format)
            raw_desc = row[desc_idx].strip()
            if not raw_desc:
                raise ValueError(f"Linha {row_num} sem descrição.")

            parsed_cents = parse_brl_to_cents(row[amt_idx], decimal_sep=decimal_sep)
            if expense_sign == "positive":
                raw_amount_cents = -parsed_cents
            else:
                raw_amount_cents = parsed_cents

            occ_key = (raw_date, raw_amount_cents, raw_desc)
            occurrence_counter[occ_key] += 1
            occ_idx = occurrence_counter[occ_key]

            dedup_hash = compute_dedup_hash(
                account_id, raw_date, raw_amount_cents, raw_desc, occ_idx
            )
            is_duplicate = dedup_hash in existing_hashes

            # Installments are NOT inferred from DD/MM-like text in bank statements.
            inst_curr = inst_total = None
            inst_group_key = None

            # Default kind based on sign and account type
            if raw_amount_cents < 0:
                kind = "expense"
            else:
                norm_desc = normalize_text(raw_desc)
                if account["account_type"] == "credit_card" and any(
                    hint in norm_desc for hint in CREDIT_BILL_PAYMENT_HINTS
                ):
                    kind = "transfer"
                else:
                    kind = "income"

            display_name = raw_desc
            category_id = None
            matched_rule_name = None

            rule = find_matching_rule(conn, raw_desc)
            if rule:
                display_name = rule["target_display_name"]
                if rule["target_category_id"] is not None:
                    category_id = int(rule["target_category_id"])
                if rule["target_kind"] is not None:
                    kind = rule["target_kind"]
                matched_rule_name = rule["pattern"]

            row_month = raw_date[:7]
            observed_months.append(row_month)

            raw_obj = (
                dict(zip(headers, row)) if headers is not None else {str(i): v for i, v in enumerate(row)}
            )

            parsed_rows.append(
                {
                    "row_index": len(parsed_rows),
                    "raw_date": raw_date,
                    "raw_description": raw_desc,
                    "raw_amount_cents": raw_amount_cents,
                    "raw_csv_row": json.dumps(raw_obj, ensure_ascii=False),
                    "dedup_hash": dedup_hash,
                    "is_duplicate": is_duplicate,
                    "display_name": display_name,
                    "category_id": category_id,
                    "category_name": categories_by_id[category_id]["name"] if category_id in categories_by_id else None,
                    "category_color": categories_by_id[category_id]["color"] if category_id in categories_by_id else None,
                    "kind": kind,
                    "installment_current": inst_curr,
                    "installment_total": inst_total,
                    "installment_group_key": inst_group_key,
                    "matched_rule": matched_rule_name,
                    "competence_month": row_month,
                }
            )
        except Exception as exc:
            errors.append(f"Linha {row_num}: {exc}")

    suggested_month = competence_month
    if not suggested_month:
        suggested_month = max(observed_months) if observed_months else current_month()

    # For credit cards, assign the invoice's competence_month to all rows
    if account["account_type"] == "credit_card":
        for item in parsed_rows:
            item["competence_month"] = suggested_month

    new_count = sum(1 for r in parsed_rows if not r["is_duplicate"])
    dup_count = sum(1 for r in parsed_rows if r["is_duplicate"])

    return {
        "account": dict(account),
        "encoding": used_encoding,
        "rows": parsed_rows,
        "errors": errors,
        "new_count": new_count,
        "duplicate_count": dup_count,
        "suggested_competence_month": suggested_month,
    }


def commit_csv_import(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    profile_id: int | None,
    filename: str,
    competence_month: str | None,
    rows: list[dict[str, Any]],
    selected_indices: set[int] | None = None,
) -> dict[str, Any]:
    to_insert = []
    for r in rows:
        if selected_indices is not None:
            if r["row_index"] not in selected_indices:
                continue
        elif r.get("is_duplicate"):
            continue
        to_insert.append(r)

    if not to_insert:
        return {"batch_id": None, "imported_count": 0, "skipped_count": len(rows)}

    cur = conn.execute(
        """
        INSERT INTO import_batches (account_id, profile_id, filename, competence_month, row_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (account_id, profile_id, filename, competence_month, len(to_insert)),
    )
    batch_id = int(cur.lastrowid)

    for r in to_insert:
        # If user manually forced importing a duplicate row, append batch suffix so future re-imports still stay consistent
        dedup_hash = r["dedup_hash"]
        if r.get("is_duplicate"):
            dedup_hash = f"{dedup_hash}#b{batch_id}"

        conn.execute(
            """
            INSERT INTO transactions (
                account_id, import_batch_id, raw_date, raw_description, raw_amount_cents,
                raw_csv_row, dedup_hash, competence_month, display_name, category_id,
                kind, installment_current, installment_total, installment_group_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                batch_id,
                r["raw_date"],
                r["raw_description"],
                int(r["raw_amount_cents"]),
                r.get("raw_csv_row"),
                dedup_hash,
                r["competence_month"],
                r["display_name"],
                r.get("category_id"),
                r["kind"],
                r.get("installment_current"),
                r.get("installment_total"),
                r.get("installment_group_key"),
            ),
        )

    return {
        "batch_id": batch_id,
        "imported_count": len(to_insert),
        "skipped_count": len(rows) - len(to_insert),
    }


def delete_import_batch_with_details(conn: sqlite3.Connection, batch_id: int) -> dict[str, int]:
    from app.services.bills import reconcile_links_after_card_changes

    row = conn.execute(
        """
        SELECT ib.row_count, a.account_type
        FROM import_batches ib JOIN accounts a ON a.id = ib.account_id
        WHERE ib.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if not row:
        return {"removed_count": 0, "reverted_payments": 0}

    affected: list[tuple[int, str]] = []
    if row["account_type"] == "credit_card":
        affected = [
            (int(r["account_id"]), r["competence_month"])
            for r in conn.execute(
                """
                SELECT DISTINCT account_id, competence_month
                FROM transactions WHERE import_batch_id = ?
                """,
                (batch_id,),
            ).fetchall()
        ]

    conn.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))

    reverted = 0
    for acc_id, comp_month in affected:
        reverted += reconcile_links_after_card_changes(conn, acc_id, comp_month)
    return {"removed_count": int(row["row_count"]), "reverted_payments": reverted}


def delete_import_batch(conn: sqlite3.Connection, batch_id: int) -> int:
    return delete_import_batch_with_details(conn, batch_id)["removed_count"]
