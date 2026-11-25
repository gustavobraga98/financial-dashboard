from __future__ import annotations

import re
from datetime import date

MONTH_NAMES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MONTH_SHORT_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def format_brl(cents: int | None, show_sign: bool = False) -> str:
    if cents is None:
        return "R$ 0,00"
    sign = ""
    if cents < 0:
        sign = "-"
    elif show_sign and cents > 0:
        sign = "+"
    abs_cents = abs(int(cents))
    reais = abs_cents // 100
    centavos = abs_cents % 100
    reais_fmt = f"{reais:,}".replace(",", ".")
    return f"{sign}R$ {reais_fmt},{centavos:02d}"


def format_brl_input(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    abs_cents = abs(int(cents))
    return f"{sign}{abs_cents // 100},{abs_cents % 100:02d}"


def parse_brl_to_cents(raw: str | int | float | None, decimal_sep: str | None = None) -> int:
    if raw is None:
        return 0
    if isinstance(raw, int):
        return raw * 100
    if isinstance(raw, float):
        return round(raw * 100)

    text = str(raw).strip()
    if not text:
        return 0

    text = text.replace("R$", "").replace("\u00a0", "").replace(" ", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    if decimal_sep == ",":
        text = text.replace(".", "").replace(",", ".")
    elif decimal_sep == ".":
        text = text.replace(",", "")
    else:
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")

    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", text):
        raise ValueError(f"Valor monetário inválido: {raw!r}")

    return round(float(text) * 100)


def current_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def parse_month(month: str) -> tuple[int, int]:
    year_s, month_s = month.split("-")
    year, m = int(year_s), int(month_s)
    if not (1 <= m <= 12):
        raise ValueError(f"Mês inválido: {month}")
    return year, m


def shift_month(month: str, delta: int) -> str:
    year, m = parse_month(month)
    total = year * 12 + (m - 1) + delta
    new_year = total // 12
    new_month = (total % 12) + 1
    return f"{new_year:04d}-{new_month:02d}"


def months_between(start_month: str, end_month: str) -> int:
    y1, m1 = parse_month(start_month)
    y2, m2 = parse_month(end_month)
    return (y2 * 12 + m2) - (y1 * 12 + m1)


def month_label(month: str, short: bool = False) -> str:
    year, m = parse_month(month)
    if short:
        return f"{MONTH_SHORT_PT[m]}/{str(year)[2:]}"
    return f"{MONTH_NAMES_PT[m]} {year}"


def format_date_br(iso_date: str | None) -> str:
    if not iso_date:
        return "—"
    parts = iso_date.split("-")
    if len(parts) != 3:
        return iso_date
    return f"{parts[2]}/{parts[1]}/{parts[0]}"
