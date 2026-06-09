#!/usr/bin/env python3
"""
Data Journal Discovery Script v3 — Targeted approach

Strategies (ordered by reliability):
1. DOAJ API: search journals with "data paper" or "data descriptor" in description/tags
2. OpenAlex: find works with "data paper" in title AND "data journal" in source description
3. Known publisher lists: check Pensoft, Ubiquity Press, Elsevier for new data journals
4. Crossref: find journals whose title contains "data journal" patterns

Outputs JSON candidates for manual review.
"""

import csv
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("Install requests: pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, ".."))
CSV_PATH = os.path.join(ROOT, "data_journals_characteristics.csv")
CANDIDATES_PATH = os.path.join(ROOT, "data", "candidates.json")
UA = "DataJournalRegistry/1.0 (https://harrytyp.github.io/data-journals)"


def load_existing_issns():
    """Return set of normalized ISSNs already in registry."""
    s = set()
    try:
        with open(CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                issn = (row.get("ISSN") or "").strip()
                if issn and issn != "(pending)":
                    s.add(issn.replace("-", "").upper().strip())
    except FileNotFoundError:
        pass
    return s


def is_new(raw, existing):
    return raw.replace("-", "").upper().strip() not in existing if raw else False


def doaj_discover(existing):
    """Query DOAJ API for journals related to data papers."""
    print("\n=== DOAJ Discovery ===")
    candidates = {}
    seen = set()

    # DOAJ API v3 — search by keyword (path-based: /api/v3/search/journals/{query})
    for keyword in ['data paper', 'data journal', 'data brief', 'data descriptor']:
        params = {
            "pageSize": 50,
            "page": 1,
        }
        try:
            encoded = urllib.parse.quote(keyword)
            r = requests.get(
                f"https://doaj.org/api/v3/search/journals/{encoded}",
                params=params,
                headers={"User-Agent": UA},
                timeout=20,
            )
            if r.status_code != 200:
                print(f"  DOAJ error {r.status_code} for '{keyword}'")
                continue

            data = r.json()
            results = data.get("results", [])
            total = data.get("total", 0)
            print(f"  '{keyword}': {total} total, showing {len(results)}")

            for j in results:
                bib = j.get("bibjson", j) or {}
                pissn = (bib.get("pissn") or "").strip()
                eissn = (bib.get("eissn") or "").strip()
                issn = pissn or eissn
                if not issn or not is_new(issn, existing):
                    continue
                if not issn or not is_new(issn, existing):
                    continue
                n = issn.replace("-", "").upper()
                if n in seen:
                    continue
                seen.add(n)

                title = (bib.get("title") or "").strip()
                publisher = (bib.get("publisher") or j.get("publisher") or "").strip()
                homepage = (bib.get("url") or j.get("homepage_url") or "").strip()
                subjects = []
                for subj in (j.get("subject") or []):
                    if isinstance(subj, dict):
                        subjects.append(subj.get("term", ""))
                    elif isinstance(subj, str):
                        subjects.append(subj)

                candidates[n] = {
                    "issn": issn,
                    "journal_title": title,
                    "publisher": publisher,
                    "url": homepage or "",
                    "source": f"doaj-keyword:{keyword}",
                    "evidence": f"DOAJ keyword search: '{keyword}'",
                    "doaj_subjects": subjects[:5],
                }

            time.sleep(0.5)
        except Exception as e:
            print(f"  Error: {e}")

    return list(candidates.values())


def openalex_data_paper_titles(existing):
    """
    Find works whose title includes 'data paper' or 'data descriptor',
    then extract the source journal. Count works per journal to find
    dedicated data journal venues.
    """
    print("\n=== OpenAlex: Journals publishing data-paper-titled works ===")
    candidates = {}
    journal_counts = {}

    for query in ['"data paper"', '"data descriptor"', '"data article"']:
        try:
            params = {
                "filter": f"title_and_abstract.search:{urllib.parse.quote(query)}",
                "per_page": 50,
                "sort": "publication_year:desc",
                "select": "id,primary_location,publication_year,type",
            }
            r = requests.get(
                "https://api.openalex.org/works",
                params=params,
                headers={"User-Agent": UA},
                timeout=20,
            )
            if r.status_code != 200:
                print(f"  OpenAlex error {r.status_code} for '{query}'")
                continue

            data = r.json()
            results = data.get("results", [])
            total = data.get("meta", {}).get("count", 0)
            print(f"  '{query}': {total} works (page: {len(results)})")

            for w in results:
                loc = w.get("primary_location", {}) or {}
                src = loc.get("source")
                if not src:
                    continue
                issn_list = src.get("issn", [])
                if not issn_list:
                    continue
                issn = issn_list[0]
                n = issn.replace("-", "").upper()
                journal_counts[n] = journal_counts.get(n, 0) + 1
                if n not in candidates:
                    candidates[n] = {
                        "issn": issn,
                        "journal_title": src.get("display_name", "?"),
                        "publisher": src.get("host_organization_name", "") or "?",
                        "url": src.get("homepage_url", "") or "",
                        "data_paper_works": 0,
                        "matched_terms": [],
                    }
                if query not in candidates[n]["matched_terms"]:
                    candidates[n]["matched_terms"].append(query)

            time.sleep(0.3)
        except Exception as e:
            print(f"  Error: {e}")

    # Update counts
    for n, c in candidates.items():
        c["data_paper_works"] = journal_counts.get(n, 0)
        c["evidence"] = f"OpenAlex: {c['data_paper_works']} works matching {', '.join(c['matched_terms'])}"

    # Filter: journals with at least 3 data-paper works are promising
    promising = [c for c in candidates.values() if c["data_paper_works"] >= 3 and is_new(c["issn"], existing)]
    others = [c for c in candidates.values() if c["data_paper_works"] < 3 or not is_new(c["issn"], existing)]

    print(f"  Promising candidates (≥3 data-paper works): {len(promising)}")
    return promising + others


def title_pattern_discovery(existing):
    """
    Find journals whose title follows data journal naming conventions.
    Query OpenAlex sources by title pattern.
    """
    print("\n=== Title Pattern Discovery ===")
    candidates = {}
    seen = set()

    patterns = [
        '"Data Journal"',
        '"Data Papers"',
        '"Data in"',
        '"Data Brief"',
        '"Journal of Data"',
        '"Research Data"',
        '"Open Data"',
        '"Data Science" AND journal',
    ]

    for pattern in patterns:
        try:
            params = {
                "search": pattern,
                "per_page": 25,
                "sort": "relevance",
                "select": "id,display_name,issn,host_organization_name,homepage_url,type",
            }
            r = requests.get(
                "https://api.openalex.org/sources",
                params=params,
                headers={"User-Agent": UA},
                timeout=20,
            )
            if r.status_code != 200:
                print(f"  OpenAlex error {r.status_code} for '{pattern}'")
                continue

            sources = r.json().get("results", [])
            for src in sources:
                if src.get("type") not in ("journal", None):
                    continue
                issn_list = src.get("issn", [])
                if not issn_list:
                    continue
                issn = issn_list[0]
                if not is_new(issn, existing):
                    continue
                n = issn.replace("-", "").upper()
                if n in seen:
                    continue
                seen.add(n)
                candidates[n] = {
                    "issn": issn,
                    "journal_title": src.get("display_name", "?"),
                    "publisher": src.get("host_organization_name", "") or "?",
                    "url": src.get("homepage_url", "") or "",
                    "source": "title-pattern",
                    "evidence": f"OpenAlex source search: '{pattern}'",
                }

            time.sleep(0.3)
        except Exception as e:
            print(f"  Error: {e}")

    return list(candidates.values())


def verify_candidates(candidates):
    """Verify via OpenAlex, add metadata. Sort by promise."""
    print(f"\n=== Verifying {len(candidates)} candidates ===")
    results = []

    for c in candidates:
        issn = c.get("issn", "")
        if not issn:
            continue
        try:
            r = requests.get(
                f"https://api.openalex.org/sources?filter=issn:{issn}",
                headers={"User-Agent": UA},
                timeout=15,
            )
            if r.status_code == 200:
                srcs = r.json().get("results", [])
                if srcs:
                    s = srcs[0]
                    c["type"] = s.get("type")
                    c["works_count"] = s.get("works_count", 0)
                    c["cited_by_count"] = s.get("cited_by_count", 0)
                    c["verified"] = s.get("type") == "journal"
                else:
                    c["verified"] = False
            else:
                c["verified"] = False
            time.sleep(0.15)
        except Exception as e:
            c["verified"] = False
            c["verify_error"] = str(e)
        results.append(c)

    return results


def main():
    print("=" * 60)
    print("Data Journal Discovery v3")
    print(f"Date: {datetime.now().isoformat()}")
    print("=" * 60)

    existing = load_existing_issns()
    print(f"\nExisting: {len(existing)} ISSNs")

    # Run strategies
    doaj = doaj_discover(existing)
    oa_titles = openalex_data_paper_titles(existing)
    patterns = title_pattern_discovery(existing)

    # Merge by ISSN
    seen = {}
    for clist in [doaj, oa_titles, patterns]:
        for c in clist:
            n = c["issn"].replace("-", "").upper()
            if n not in seen:
                seen[n] = c
            else:
                seen[n]["source"] += f", {c['source']}"

    all_candidates = list(seen.values())
    print(f"\nTotal unique candidates: {len(all_candidates)}")

    # Verify
    verified = verify_candidates(all_candidates)
    journals = [c for c in verified if c.get("verified")]
    others = [c for c in verified if not c.get("verified")]

    print(f"  Confirmed journals: {len(journals)}")
    print(f"  Unconfirmed: {len(others)}")

    # Sort: works_count descending for journals
    journals.sort(key=lambda c: c.get("works_count", 0), reverse=True)

    result = {
        "generated": datetime.now().isoformat(),
        "existing_count": len(existing),
        "candidates": journals + others,
        "notes": (
            "All candidates need manual verification. "
            "'verified' means ISSN resolves in OpenAlex as a journal — "
            "NOT that it qualifies as a data journal."
        ),
    }

    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {CANDIDATES_PATH}")

    if journals:
        print(f"\n{'='*60}")
        print("CANDIDATE DATA JOURNALS (top by works count):")
        print(f"{'='*60}")
        for c in journals[:30]:
            dp = c.get("data_paper_works", 0)
            wc = c.get("works_count", 0)
            print(f"  {c['issn']:<10} {c['journal_title'][:55]:<55} w:{wc:<6}", end="")
            if dp:
                print(f" dp:{dp}", end="")
            print()

    return 0


if __name__ == "__main__":
    main()
