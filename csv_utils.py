"""Shared, case-insensitive ASIN CSV reading, so 'ASIN'/'asin'/'Asin' headers
(and a missing 'label' column) all work the same everywhere they're read."""

import csv


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
            rows.append({"asin": asin, "label": label})
        return rows
