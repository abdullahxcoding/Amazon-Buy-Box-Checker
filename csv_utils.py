"""Shared, case-insensitive ASIN CSV reading, so 'ASIN'/'asin'/'Asin' headers
(and missing 'label'/'expected_price' columns) all work the same everywhere
they're read."""

import csv


def _parse_price(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    raw = raw.replace("£", "").replace(",", "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def read_asin_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            lower = {(k or "").strip().lower(): v for k, v in row.items() if k}
            asin = (lower.get("asin") or "").strip()
            if not asin:
                continue
            label = (lower.get("label") or "").strip()
            expected_price = _parse_price(lower.get("expected_price") or lower.get("price") or "")
            rows.append({"asin": asin, "label": label, "expected_price": expected_price})
        return rows
