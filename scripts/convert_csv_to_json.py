#!/usr/bin/env python3
"""
Convert data_journals_characteristics.csv to data/journals.json
Run this after updating the CSV.
"""

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CSV_PATH = os.path.join(ROOT, "data_journals_characteristics.csv")
JSON_PATH = os.path.join(ROOT, "data", "journals.json")

rows = []
with open(CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        row = {k.strip(): v.strip() for k, v in r.items() if k.strip()}
        if row.get('ISSN'):
            rows.append(row)

os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
with open(JSON_PATH, 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

print(f"✓ Converted {len(rows)} journals to {JSON_PATH}")
