#!/usr/bin/env python3
"""
Data Journal Discovery via OpenAlex-Vollabzug

Lädt OpenAlex-Sources via API (cursor-basiert),
filtert auf Journals, bewertet mit einem Signal-basierten Score,
und gibt Kandidaten aus, die manuell geprüft werden können.

Usage:
    python discover_candidates.py [--max N] [--max-pages M]

--max:       Stop scanning once we have at least N candidates (default: 300)
--max-pages: Hard limit on API pages to prevent runaway scans (default: 2000)
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, ".."))
CSV_PATH = os.path.join(ROOT, "data_journals_characteristics.csv")
CANDIDATES_PATH = os.path.join(ROOT, "data", "candidates.json")
UA = "DataJournalRegistry/1.0 (https://github.com/harrytyp/data-journals)"


def load_existing():
    s = {}
    try:
        with open(CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                issn = (row.get("ISSN") or "").strip()
                if issn and issn != "(pending)":
                    s[issn.replace("-", "").upper()] = row.get("data_journal_type", "?")
    except FileNotFoundError:
        pass
    return s


# Bekannte Verlage, bei denen Data Journals erscheinen
DJ_PUBLISHERS = [
    "pensoft", "ubiquity press", "copernicus", "brill", "iop publishing",
    "iop", "sage publishing", "taylor & francis", "springer nature",
    "elsevier", "frontiers", "mdpi", "oxford university press",
    "f1000", "elm", "caltech library", "university of stuttgart",
    "université de lorraine", "dariah", "wiley", "blackwell",
]

# Data-Journal-Schlüsselwörter im Titel
DJ_TITLE_KW = [
    "data journal", "research data", "data paper", "data brief",
    "data descriptor", "digital curation", "data intelligence",
    "scientific data", "geoscience data", "earth system science data",
    "data in brief", "chemical data", "nuclear data",
    "astronomical data", "viticulture data", "biodiversity data",
    "data science", "open data", "big data", "database journal",
    "data & knowledge", "data and information", "data technologies",
    "data engineering", "genomic data", "data mining",
]

# Data-Journal-Topic-Signale (Subfields/Fields)
DJ_TOPICS = [
    "research data management", "scientific computing and data",
    "metadata", "data management", "data curation", "data publishing",
    "digital curation", "data sharing", "data science",
    "information science", "library science", "digital libraries",
]


def score_source(src):
    """Bewertet eine OpenAlex-Source auf Data-Journal-Potential."""
    name = (src.get("display_name") or "").lower()
    publisher = (src.get("host_organization_name") or "").lower()
    topics = [t.get("display_name", "").lower() for t in (src.get("topics") or []) if isinstance(t, dict)]
    issn_list = src.get("issn") or []
    source_type = src.get("type", "")

    if source_type != "journal":
        return None
    if not name:
        return None
    if not issn_list:
        return None

    signals = []
    score = 0.0

    # Signal 1: Data-Journal-Keywords im Titel
    for kw in DJ_TITLE_KW:
        if kw in name:
            signals.append(f"title:{kw}")
            score += 2.0
            break  # max 1 Titel-Signal

    # Signal 2: Publisher-Bekanntheit
    for pub in DJ_PUBLISHERS:
        if pub in publisher:
            signals.append(f"pub:{pub}")
            score += 0.8
            break

    # Signal 3: Topic-Signale
    for t in topics:
        for djt in DJ_TOPICS:
            if djt in t:
                signals.append(f"topic:{t[:40]}")
                score += 0.5
                break

    # Signal 4: "Data" im Namen + minimum works (nicht zu klein)
    # Aber nicht: wenn nur "data" im Namen ohne andere Signale
    if "data" in name and score < 1.0:
        # Nur aufnehmen, wenn es eindeutig klingt
        if any(kw in name for kw in ["data", "dataset"]):
            score += 0.3
            signals.append("generic:data-in-title")

    # Signal 5: Wenn der Titel "Journal of Data" oder "... Data" enthält
    if "data" in name and ("journal" in name or "review" in name or "letters" in name):
        score += 0.5
        signals.append("pattern:journal-of-data")

    # Mindestschwelle
    if score >= 1.5:
        return {
            "issn": issn_list[0],
            "journal_title": src.get("display_name", "?"),
            "publisher": src.get("host_organization_name", "") or "?",
            "url": src.get("homepage_url", "") or "",
            "works_count": src.get("works_count", 0) or 0,
            "type": source_type,
            "score": round(score, 2),
            "signals": signals,
        }
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Discover data journal candidates via OpenAlex API"
    )
    parser.add_argument(
        "--max", type=int, default=300,
        help="Stop scanning once we have at least N candidates (default: 300)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=2000,
        help="Hard limit on API pages to prevent runaway scans (default: 2000)"
    )
    args = parser.parse_args()
    target_candidates = args.max
    max_pages = args.max_pages
    # Keep scanning beyond target so we have a rich pool to sort from
    stop_after = max(target_candidates * 2, 500)

    print("=" * 60)
    print(f"Data Journal Discovery — OpenAlex Scan")
    print(f"  {datetime.now().isoformat()}")
    print(f"  Target: at least {target_candidates} candidates")
    print(f"  Max pages: {max_pages}")
    print("=" * 60)

    existing = load_existing()
    print(f"  Already in registry: {len(existing)} ISSNs")

    # OpenAlex Sources via Cursor-Pagination
    cursor = "*"
    page = 0
    candidates = {}
    total_processed = 0
    total_journals = 0
    consecutive_errors = 0
    max_retries = 3

    while cursor and page < max_pages:
        url = (f"https://api.openalex.org/sources?cursor={cursor}&per_page=200"
               f"&select=id,display_name,issn,host_organization_name,homepage_url,"
               f"works_count,type,topics")
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200:
                consecutive_errors += 1
                if consecutive_errors > max_retries:
                    print(f"  ⚠ Too many errors ({consecutive_errors}), "
                          f"skipping remaining pages")
                    break
                wait = 10 * consecutive_errors
                print(f"  HTTP {r.status_code} (attempt {consecutive_errors}/"
                      f"{max_retries}), waiting {wait}s...")
                time.sleep(wait)
                continue

            consecutive_errors = 0
            data = r.json()
            meta = data.get("meta", {})
            cursor = meta.get("next_cursor")
            page += 1
            results = data.get("results", [])

            for src in results:
                total_processed += 1
                if src.get("type") != "journal":
                    continue
                total_journals += 1

                issn_list = src.get("issn") or []
                if not issn_list:
                    continue
                normalized = issn_list[0].replace("-", "").upper()
                if normalized in existing:
                    continue

                result = score_source(src)
                if result:
                    candidates[normalized] = result

            if page % 50 == 0 or page == max_pages:
                print(f"  Page {page}: {total_processed:,} processed, "
                      f"{total_journals:,} journals, {len(candidates)} candidates")

            # Early exit once we have enough candidates
            if len(candidates) >= stop_after:
                print(f"  ✓ Reached {len(candidates)} candidates, stopping scan")
                cursor = None  # break the while loop

            time.sleep(0.15)  # Rate limiting

        except requests.exceptions.Timeout:
            consecutive_errors += 1
            if consecutive_errors > max_retries:
                print(f"  ⚠ Too many timeouts ({consecutive_errors}), giving up")
                break
            print(f"  ⏱ Timeout (attempt {consecutive_errors}/{max_retries}), "
                  f"retrying...")
            time.sleep(5 * consecutive_errors)
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors > max_retries:
                print(f"  ⚠ Too many errors ({consecutive_errors}), giving up: {e}")
                break
            print(f"  Error: {e} (attempt {consecutive_errors}/{max_retries})")
            time.sleep(5 * consecutive_errors)

    # Sortieren nach Score
    sorted_candidates = sorted(candidates.values(), key=lambda c: -c["score"])

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"  {total_processed:,} sources processed")
    print(f"  → {total_journals:,} journals")
    print(f"  → {len(sorted_candidates)} candidates (score ≥ 1.5, not in registry)")
    print(f"  Scanned {page} pages")
    # Only report early stop if applicable
    if len(candidates) >= stop_after:
        print(f"  ⏹ Early stop at page {page} (hit candidate target)")
    elif page >= max_pages:
        print(f"  ⏹ Stopped at page limit ({max_pages})")
    print(f"{'='*60}")

    # Top list
    for c in sorted_candidates[:30]:
        signals = "; ".join(c["signals"][:3])
        w = c.get("works_count", 0) or 0
        print(f"\n  S{c['score']:.1f} {c['issn']:<12} {c['journal_title'][:60]}")
        print(f"      {c.get('publisher','?'):<50} Works:{w:<8}")
        print(f"      Signals: {signals}")

    # Save results (trim to max target)
    trimmed = sorted_candidates[:target_candidates]
    output = {
        "generated": datetime.now().isoformat(),
        "method": "OpenAlex sources API scan via cursor pagination",
        "total_sources_processed": total_processed,
        "total_journals": total_journals,
        "pages_scanned": page,
        "existing_count": len(existing),
        "candidates": trimmed,
        "verified_candidates": len(trimmed),
        "unverified_candidates": 0,
        "note": "Alle Kandidaten benötigen manuelle Prüfung pro CONTRIBUTING.md-Kriterien.",
    }
    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n→ Saved: {CANDIDATES_PATH} ({len(trimmed)} candidates)")
    return 0


if __name__ == "__main__":
    main()
