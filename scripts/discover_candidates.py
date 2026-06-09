#!/usr/bin/env python3
"""
Data Journal Discovery Script

Uses Crossref and OpenAlex APIs to find potential data journals
not yet in the registry. Outputs candidate journals for manual review.

Usage:
    python scripts/discover_candidates.py [--output data/candidates.json]

Requirements:
    requests (pip install requests)
"""

import json
import os
import sys
import time
import urllib.parse
import argparse
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests")
    sys.exit(1)

# Load existing registry
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
CSV_PATH = os.path.join(REPO_ROOT, "data_journals_characteristics.csv")
CANDIDATES_PATH = os.path.join(REPO_ROOT, "data", "candidates.json")

def load_existing_issns():
    """Load currently registered ISSNs from the CSV."""
    issns = set()
    import csv
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                issn = row.get('ISSN', '').strip()
                if issn and issn != '(pending)':
                    # Normalize ISSN: remove hyphen for comparison
                    issns.add(issn.replace('-', '').upper())
                    issns.add(issn.upper())
    except FileNotFoundError:
        print(f"Warning: {CSV_PATH} not found, continuing with empty registry")
    return issns


def discover_via_crossref(existing_issns, max_results=200):
    """
    Query Crossref for works of type 'data-paper' or with 'data paper' in title.
    Returns set of candidate ISSN-L + journal title pairs.
    """
    print(f"\n=== Crossref Discovery (max {max_results} results) ===")
    candidates = {}

    # Strategy 1: Works with type "data-paper"
    base_url = "https://api.crossref.org/works"
    params = {
        "filter": "type:data-paper",
        "rows": min(max_results, 100),
        "sort": "published",
        "order": "desc",
    }

    try:
        resp = requests.get(base_url, params=params, timeout=30,
                            headers={"User-Agent": "DataJournalRegistry/1.0 (mailto:data-journals@example.org)"})
        if resp.status_code != 200:
            print(f"  Crossref API error: {resp.status_code}")
        else:
            data = resp.json()
            items = data.get('message', {}).get('items', [])
            print(f"  Found {len(items)} data-paper type works")

            for item in items:
                issn = _extract_issn(item)
                title = _extract_journal_title(item)
                if issn and issn not in existing_issns:
                    normalized = issn.replace('-', '').upper()
                    if normalized not in existing_issns:
                        key = normalized
                        if key not in candidates:
                            publisher = _extract_publisher(item)
                            candidates[key] = {
                                "issn": issn,
                                "journal_title": title,
                                "publisher": publisher,
                                "source": "crossref-data-paper-type",
                                "evidence": f"Crossref type:data-paper — {item.get('title', ['?'])[0][:80]}",
                                "url": _extract_url(item)
                            }

            time.sleep(0.5)  # Rate limiting
    except Exception as e:
        print(f"  Error querying Crossref: {e}")

    # Strategy 2: Search for "data paper" in title
    params2 = {
        "query.title": "data paper",
        "rows": min(max_results, 100),
        "sort": "published",
        "order": "desc",
    }
    try:
        resp2 = requests.get(base_url, params=params2, timeout=30,
                             headers={"User-Agent": "DataJournalRegistry/1.0 (mailto:data-journals@example.org)"})
        if resp2.status_code == 200:
            items2 = resp2.json().get('message', {}).get('items', [])
            print(f"  Found {len(items2)} works with 'data paper' in title")
            for item in items2:
                issn = _extract_issn(item)
                if issn:
                    normalized = issn.replace('-', '').upper()
                    if normalized not in existing_issns and normalized not in candidates:
                        title = _extract_journal_title(item)
                        publisher = _extract_publisher(item)
                        candidates[normalized] = {
                            "issn": issn,
                            "journal_title": title,
                            "publisher": publisher,
                            "source": "crossref-title-search",
                            "evidence": f"Crossref title search — '{item.get('title', ['?'])[0][:80]}'",
                            "url": _extract_url(item)
                        }
    except Exception as e:
        print(f"  Error querying Crossref title: {e}")

    return list(candidates.values())


def discover_via_openalex(existing_issns, max_results=200):
    """
    Query OpenAlex for journals/concepts related to data journals.
    """
    print(f"\n=== OpenAlex Discovery (max {max_results} results) ===")
    candidates = {}
    seen_candidates = set()

    # Strategy 1: Search for "data journal" in source display name
    base_url = "https://api.openalex.org/sources"
    params = {
        "search": "data journal",
        "per_page": min(max_results, 50),
        "sort": "cited_by_count",
        "order": "desc",
    }

    try:
        resp = requests.get(base_url, params=params, timeout=30,
                            headers={"User-Agent": "DataJournalRegistry/1.0"})
        if resp.status_code != 200:
            print(f"  OpenAlex API error: {resp.status_code}")
        else:
            data = resp.json()
            sources = data.get('results', [])
            print(f"  Found {len(sources)} sources matching 'data journal'")

            for src in sources:
                issn_list = src.get('issn', [])
                issn = issn_list[0] if issn_list else None
                normalized = issn.replace('-', '').upper() if issn else None

                if normalized and normalized not in existing_issns and normalized not in seen_candidates:
                    seen_candidates.add(normalized)
                    title = src.get('display_name', '?')
                    publisher = src.get('host_organization_name', '?') or '?'
                    homepage = src.get('homepage_url', '')
                    candidates[normalized] = {
                        "issn": issn,
                        "journal_title": title,
                        "publisher": publisher,
                        "source": "openalex-search",
                        "evidence": f"OpenAlex source search — '{title}' matches 'data journal'",
                        "url": homepage
                    }

            time.sleep(0.3)
    except Exception as e:
        print(f"  Error querying OpenAlex: {e}")

    # Strategy 2: Find works with "data paper" concept, extract sources
    params2 = {
        "filter": "concepts.display_name:data+papers",
        "per_page": min(max_results, 50),
        "sort": "cited_by_count",
        "order": "desc",
    }
    try:
        resp2 = requests.get("https://api.openalex.org/works", params=params2, timeout=30,
                             headers={"User-Agent": "DataJournalRegistry/1.0"})
        if resp2.status_code == 200:
            works = resp2.json().get('results', [])
            print(f"  Found {len(works)} works tagged with 'data papers' concept")
            for w in works:
                src = w.get('primary_location', {}).get('source')
                if src:
                    issn_list = src.get('issn', [])
                    issn = issn_list[0] if issn_list else None
                    if issn:
                        normalized = issn.replace('-', '').upper()
                        if normalized not in existing_issns and normalized not in seen_candidates:
                            seen_candidates.add(normalized)
                            title = src.get('display_name', '?')
                            publisher = src.get('host_organization_name', '?') or '?'
                            candidates[normalized] = {
                                "issn": issn,
                                "journal_title": title,
                                "publisher": publisher,
                                "source": "openalex-concept",
                                "evidence": f"OpenAlex concept 'data papers' — work '{w.get('title', '?')[:60]}'",
                                "url": src.get('homepage_url', '')
                            }
    except Exception as e:
        print(f"  Error querying OpenAlex works: {e}")

    return list(candidates.values())


def _extract_issn(item):
    """Extract ISSN from a Crossref API item."""
    issn = None
    # Try ISSN-L first (most canonical)
    issn_l = item.get('ISSN')
    if issn_l:
        issn = issn_l[0]
    if not issn:
        container = item.get('container-title', [])
        if container and len(container) > 1:
            # Sometimes in other fields
            pass
    return issn


def _extract_journal_title(item):
    """Extract journal/conference title from a Crossref item."""
    container = item.get('container-title', [])
    if container:
        return container[0]
    return '?'


def _extract_publisher(item):
    """Extract publisher from a Crossref item."""
    publisher = item.get('publisher')
    if publisher:
        return publisher
    return '?'


def _extract_url(item):
    """Extract journal URL from a Crossref item."""
    # Try URLs from the item
    urls = []
    for url_field in ['URL', 'link']:
        val = item.get(url_field)
        if val:
            if isinstance(val, list):
                for entry in val:
                    if isinstance(entry, dict) and 'URL' in entry:
                        urls.append(entry['URL'])
                    elif isinstance(entry, str):
                        urls.append(entry)
            elif isinstance(val, str):
                urls.append(val)
    return urls[0] if urls else ''


def merge_and_dedup(candidates_by_source):
    """Merge candidates from multiple sources, deduplicating by ISSN."""
    seen = {}
    for source_list in candidates_by_source:
        for c in source_list:
            issn = c.get('issn', '')
            normalized = issn.replace('-', '').upper()
            if normalized not in seen:
                seen[normalized] = c
            else:
                # Merge evidence
                existing = seen[normalized]
                if c.get('evidence') and existing.get('evidence') != c.get('evidence'):
                    existing['evidence'] += f"; {c['evidence']}"
                    if c.get('source'):
                        existing['source'] += f", {c['source']}"
    return list(seen.values())


def verify_candidates(candidates):
    """
    Quick auto-verification: try to fetch ISSN metadata for each candidate.
    This is a lightweight check; full verification requires human review.
    """
    print(f"\n=== Verifying {len(candidates)} candidates ===")
    verified = []
    for c in candidates:
        issn = c.get('issn', '')
        if not issn:
            continue

        # Check against ISSN Portal via Crossref ISSN lookup
        try:
            url = f"https://api.crossref.org/journals/{urllib.parse.quote(issn)}"
            resp = requests.get(url, timeout=15,
                                headers={"User-Agent": "DataJournalRegistry/1.0"})
            if resp.status_code == 200:
                data = resp.json().get('message', {})
                title = data.get('title', '')
                publisher = data.get('publisher', '')
                if title:
                    c['crossref_title'] = title
                    c['crossref_publisher'] = publisher
                    c['verified'] = True
                else:
                    c['verified'] = False
            else:
                c['verified'] = False
                c['verify_error'] = f"ISSN lookup returned {resp.status_code}"
            time.sleep(0.3)
        except Exception as e:
            c['verified'] = False
            c['verify_error'] = str(e)

        verified.append(c)

    return verified


def main():
    parser = argparse.ArgumentParser(description="Discover potential data journals for the registry")
    parser.add_argument("--output", default=CANDIDATES_PATH,
                        help=f"Output path (default: {CANDIDATES_PATH})")
    parser.add_argument("--max", type=int, default=200,
                        help="Max results per API query (default: 200)")
    args = parser.parse_args()

    print("=" * 60)
    print("Data Journal Discovery Script")
    print(f"Date: {datetime.now().isoformat()}")
    print("=" * 60)

    existing = load_existing_issns()
    print(f"\nExisting journals: {len(existing)} ISSNs in registry")

    # Discover via multiple sources
    crossref_candidates = discover_via_crossref(existing, max_results=args.max)
    openalex_candidates = discover_via_openalex(existing, max_results=args.max)

    # Merge
    all_candidates = merge_and_dedup([crossref_candidates, openalex_candidates])
    print(f"\nTotal unique candidates: {len(all_candidates)}")

    # Lightweight verification
    verified = verify_candidates(all_candidates)

    # Separate verified from unverified
    verified_ok = [c for c in verified if c.get('verified')]
    verified_fail = [c for c in verified if not c.get('verified')]

    print(f"\n✓ Crossref-confirmed: {len(verified_ok)}")
    print(f"✗ Not confirmed via ISSN: {len(verified_fail)}")

    # Sort: verified first, then by journal title
    verified_ok.sort(key=lambda c: c.get('journal_title', '').lower())
    verified_fail.sort(key=lambda c: c.get('journal_title', '').lower())

    result = {
        "generated": datetime.now().isoformat(),
        "total_existing": len(existing),
        "total_candidates": len(all_candidates),
        "verified_candidates": len(verified_ok),
        "unverified_candidates": len(verified_fail),
        "candidates": verified_ok + verified_fail,
        "notes": "All candidates require manual verification before adding to the registry.",
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to {args.output}")

    # Summary
    if verified_ok:
        print(f"\n{'='*60}")
        print("TOP CANDIDATES (verified via ISSN):")
        print(f"{'='*60}")
        for c in verified_ok[:20]:
            print(f"  {c.get('issn','?'):<12} {c.get('journal_title','?'):<60}")
            print(f"  {'':>12} Publisher: {c.get('publisher','?'):<40}")
            print(f"  {'':>12} Source: {c.get('source','?')}")
            print()

    return 0


if __name__ == "__main__":
    main()
