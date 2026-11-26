from __future__ import annotations

import re
import sqlite3
import unicodedata

# Matches installment markers such as "02/06", "PARC 02/06", "PARCELA 3/12", "- 01/04"
_INSTALLMENT_RE = re.compile(
    r"(?:(?:\s*[-–]\s*|\s+)(?:parc(?:ela)?\.?\s*)?|\bparc(?:ela)?\.?\s*)(\d{1,2})\s*/\s*(\d{1,2})(?:\s*$|\s*\))",
    re.IGNORECASE,
)


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def extract_installment(raw_description: str) -> tuple[int | None, int | None, str]:
    """
    Extract (current, total, cleaned_description) from Brazilian credit card descriptions.
    Example: "AMAZON BR 02/06" -> (2, 6, "AMAZON BR")
    """
    text = (raw_description or "").strip()
    match = _INSTALLMENT_RE.search(text)
    if not match:
        return None, None, text

    curr = int(match.group(1))
    total = int(match.group(2))
    if not (1 <= curr <= total <= 48 and total >= 2):
        return None, None, text

    cleaned = (text[: match.start()] + text[match.end() :]).strip(" -–/()")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return curr, total, cleaned or text


def normalize_text(text: str) -> str:
    no_accents = strip_accents(text or "").lower()
    collapsed = re.sub(r"\s+", " ", no_accents).strip()
    return collapsed


def find_matching_rule(conn: sqlite3.Connection, raw_description: str) -> sqlite3.Row | None:
    norm = normalize_text(raw_description)
    if not norm:
        return None

    rules = conn.execute(
        """
        SELECT *
        FROM rules
        ORDER BY
            priority ASC,
            CASE WHEN match_type = 'exact' THEN 0 ELSE 1 END ASC,
            LENGTH(normalized_pattern) DESC,
            id ASC
        """
    ).fetchall()

    for rule in rules:
        pat = rule["normalized_pattern"]
        if not pat:
            continue
        if rule["match_type"] == "exact" and norm == pat:
            return rule
        if rule["match_type"] == "contains" and pat in norm:
            return rule
    return None


def apply_rule_row(conn: sqlite3.Connection, rule: sqlite3.Row) -> int:
    rows = conn.execute("SELECT id, raw_description, category_id, kind FROM transactions").fetchall()
    updated = 0
    pat = rule["normalized_pattern"]
    match_type = rule["match_type"]

    for tx in rows:
        norm = normalize_text(tx["raw_description"])
        matched = (match_type == "exact" and norm == pat) or (
            match_type == "contains" and pat in norm
        )
        if not matched:
            continue
        new_cat = rule["target_category_id"] if rule["target_category_id"] is not None else tx["category_id"]
        new_kind = rule["target_kind"] if rule["target_kind"] is not None else tx["kind"]
        conn.execute(
            """
            UPDATE transactions
            SET display_name = ?, category_id = ?, kind = ?
            WHERE id = ?
            """,
            (rule["target_display_name"], new_cat, new_kind, tx["id"]),
        )
        updated += 1
    return updated


def reapply_all_rules(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT id, raw_description, category_id, kind FROM transactions").fetchall()
    updated = 0
    for tx in rows:
        rule = find_matching_rule(conn, tx["raw_description"])
        if not rule:
            continue
        new_cat = rule["target_category_id"] if rule["target_category_id"] is not None else tx["category_id"]
        new_kind = rule["target_kind"] if rule["target_kind"] is not None else tx["kind"]
        conn.execute(
            """
            UPDATE transactions
            SET display_name = ?, category_id = ?, kind = ?
            WHERE id = ?
            """,
            (rule["target_display_name"], new_cat, new_kind, tx["id"]),
        )
        updated += 1
    return updated


def upsert_rule(
    conn: sqlite3.Connection,
    *,
    pattern: str,
    match_type: str,
    target_display_name: str,
    target_category_id: int | None,
    target_kind: str | None,
    priority: int = 100,
    apply_existing: bool = True,
) -> tuple[int, int]:
    norm_pat = normalize_text(pattern)
    if not norm_pat:
        raise ValueError("O padrão da regra não pode ficar vazio.")
    if match_type not in ("exact", "contains"):
        match_type = "contains"

    existing = conn.execute(
        "SELECT id FROM rules WHERE normalized_pattern = ? AND match_type = ?",
        (norm_pat, match_type),
    ).fetchone()

    if existing:
        rule_id = existing["id"]
        conn.execute(
            """
            UPDATE rules
            SET pattern = ?, target_display_name = ?, target_category_id = ?, target_kind = ?, priority = ?
            WHERE id = ?
            """,
            (pattern.strip(), target_display_name.strip(), target_category_id, target_kind, priority, rule_id),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO rules (
                pattern, normalized_pattern, match_type,
                target_display_name, target_category_id, target_kind, priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pattern.strip(),
                norm_pat,
                match_type,
                target_display_name.strip(),
                target_category_id,
                target_kind,
                priority,
            ),
        )
        rule_id = int(cur.lastrowid)

    updated = 0
    if apply_existing:
        rule = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        if rule:
            updated = apply_rule_row(conn, rule)
    return rule_id, updated
