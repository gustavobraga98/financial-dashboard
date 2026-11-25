from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path(os.environ.get("FINANCES_DB_PATH", "data/finances.db"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS banks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#1F6F5B',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('checking', 'credit_card', 'savings')),
    initial_balance_cents INTEGER NOT NULL DEFAULT 0,
    initial_balance_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(bank_id, name)
);

CREATE TABLE IF NOT EXISTS import_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    delimiter TEXT NOT NULL DEFAULT ',',
    has_header INTEGER NOT NULL DEFAULT 1,
    encoding TEXT NOT NULL DEFAULT 'utf-8-sig',
    date_column TEXT NOT NULL,
    description_column TEXT NOT NULL,
    amount_column TEXT NOT NULL,
    date_format TEXT NOT NULL DEFAULT '%Y-%m-%d',
    decimal_separator TEXT NOT NULL DEFAULT '.',
    expense_sign TEXT NOT NULL DEFAULT 'negative' CHECK (expense_sign IN ('negative', 'positive')),
    skip_rows INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES import_profiles(id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    competence_month TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#475569',
    monthly_budget_cents INTEGER
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    normalized_pattern TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'contains' CHECK (match_type IN ('exact', 'contains')),
    target_display_name TEXT NOT NULL,
    target_category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    target_kind TEXT CHECK (target_kind IN ('expense', 'income', 'transfer')),
    priority INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    import_batch_id INTEGER REFERENCES import_batches(id) ON DELETE CASCADE,
    raw_date TEXT NOT NULL,
    raw_description TEXT NOT NULL,
    raw_amount_cents INTEGER NOT NULL,
    raw_csv_row TEXT,
    dedup_hash TEXT NOT NULL,
    competence_month TEXT NOT NULL,
    display_name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('expense', 'income', 'transfer')),
    installment_current INTEGER,
    installment_total INTEGER,
    installment_group_key TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recurring_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    expected_amount_cents INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL DEFAULT 5 CHECK (day_of_month BETWEEN 1 AND 31),
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    match_keyword TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    start_month TEXT,
    end_month TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recurring_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recurring_item_id INTEGER NOT NULL REFERENCES recurring_items(id) ON DELETE CASCADE,
    competence_month TEXT NOT NULL,
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'skipped')),
    actual_amount_cents INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(recurring_item_id, competence_month)
);

CREATE INDEX IF NOT EXISTS idx_tx_competence ON transactions(competence_month);
CREATE INDEX IF NOT EXISTS idx_tx_account_month ON transactions(account_id, competence_month);
CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, raw_date);
CREATE INDEX IF NOT EXISTS idx_tx_dedup ON transactions(account_id, dedup_hash);
CREATE INDEX IF NOT EXISTS idx_tx_installment ON transactions(account_id, installment_group_key, competence_month);
CREATE INDEX IF NOT EXISTS idx_rules_norm ON rules(normalized_pattern);
"""

DEFAULT_CATEGORIES = [
    ("Moradia", "#2563EB", None),
    ("Alimentação", "#D97706", None),
    ("Mercado", "#059669", None),
    ("Transporte", "#0891B2", None),
    ("Saúde", "#DC2626", None),
    ("Assinaturas", "#7C3AED", None),
    ("Lazer", "#DB2777", None),
    ("Compras", "#EA580C", None),
    ("Educação", "#4F46E5", None),
    ("Salário / Renda", "#16A34A", None),
    ("Outros", "#64748B", None),
]

DEFAULT_PROFILES = [
    (
        "Fatura Cartão CSV (data, lançamento, valor)",
        ",",
        1,
        "utf-8-sig",
        "data",
        "lançamento",
        "valor",
        "%Y-%m-%d",
        ".",
        "positive",
        0,
    ),
    (
        "Extrato Conta TXT/CSV (DD/MM/YYYY; descrição; valor)",
        ";",
        0,
        "utf-8-sig",
        "0",
        "1",
        "2",
        "%d/%m/%Y",
        ",",
        "negative",
        0,
    ),
    (
        "Extrato CSV com cabeçalho (Data, Descrição, Valor)",
        ",",
        1,
        "utf-8-sig",
        "Data",
        "Descrição",
        "Valor",
        "%d/%m/%Y",
        ".",
        "negative",
        0,
    ),
]


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("FINANCES_DB_PATH", str(DEFAULT_DB_PATH)))


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def db_session(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)

        cat_count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if cat_count == 0:
            conn.executemany(
                "INSERT INTO categories (name, color, monthly_budget_cents) VALUES (?, ?, ?)",
                DEFAULT_CATEGORIES,
            )

        prof_count = conn.execute("SELECT COUNT(*) FROM import_profiles").fetchone()[0]
        if prof_count == 0:
            conn.executemany(
                """
                INSERT INTO import_profiles (
                    name, delimiter, has_header, encoding,
                    date_column, description_column, amount_column,
                    date_format, decimal_separator, expense_sign, skip_rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                DEFAULT_PROFILES,
            )
