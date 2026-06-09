#!/usr/bin/env python3
"""
Data Journal Discovery Script

Strategie:
  Wir suchen NICHT nach "data journal" im Titel von Journals.
  Stattdessen suchen wir nach Publikationen, deren Titel "Data Paper"
  oder "Data Descriptor" enthalten (das sind die typischen Artikel-Titel
  von Data Journals). Dann gruppieren wir nach Journal-ISSN und sehen,
  welche Journals regelmäßig solche Artikel publizieren.

Ergänzend: Suche nach Journals bei bekannten Data-Journal-Verlagen,
deren Titel "Data" enthalten und die noch nicht im Registry sind.

Usage:
    python scripts/discover_candidates.py
"""

import csv, json, os, sys, time, urllib.parse
from datetime import datetime
try:
    import requests
except ImportError:
    sys.exit("Benötigt 'requests': pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, ".."))
CSV_PATH = os.path.join(ROOT, "data_journals_characteristics.csv")
CANDIDATES_PATH = os.path.join(ROOT, "data", "candidates.json")
UA = "DataJournalRegistry/1.0 (https://github.com/harrytyp/data-journals)"


def load_existing():
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


def strategy_data_paper_titles(existing):
    """
    Strategie 1 (Primär):
    Finde Works in OpenAlex, deren Titel "Data Paper" oder ähnlich lauten.
    Das sind typische Data-Paper-Artikel. Gruppiere nach Journal (ISSN).
    Journals mit mehreren Treffern sind vielversprechend.
    """
    print("\n=== Strategie 1: Data-Paper-Titel → nach Journal gruppieren ===")
    seen = {}  # normalized ISSN → candidate
    queries = {
        '"data paper"': 'title.search:data+paper',
        '"data note"': 'title.search:data+note+AND+NOT+database',
        '"data brief"': 'title.search:data+brief',
    }

    for label, oa_filter in queries.items():
        try:
            cursor = "*"
            page = 0
            journal_counts = {}

            while cursor and page < 5:  # max 5 Seiten = ~500 Works
                url = (f"https://api.openalex.org/works?"
                       f"filter={oa_filter},type:article&per_page=100&cursor={cursor}"
                       f"&select=primary_location,publication_year&sort=publication_year:desc")
                r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
                if r.status_code != 200:
                    print(f"  Fehler {r.status_code}")
                    break
                data = r.json()
                results = data.get("results", [])
                meta = data.get("meta", {})
                cursor = meta.get("next_cursor")
                page += 1

                for w in results:
                    loc = w.get("primary_location") or {}
                    src = loc.get("source") or {}
                    issn_list = src.get("issn") or []
                    if not issn_list:
                        continue
                    issn = issn_list[0]
                    n_issn = issn.replace("-", "").upper()
                    journal_counts[n_issn] = journal_counts.get(n_issn, 0) + 1

                    if n_issn not in seen:
                        seen[n_issn] = {
                            "issn": issn,
                            "journal_title": src.get("display_name", "?"),
                            "publisher": src.get("host_organization_name", "") or "?",
                            "url": src.get("homepage_url", "") or "",
                            "matched_works": 0,
                            "sources": [],
                        }
                    if label not in seen[n_issn]["sources"]:
                        seen[n_issn]["sources"].append(label)

                time.sleep(0.3)

            # Update counts
            for n_issn, c in seen.items():
                c["matched_works"] = journal_counts.get(n_issn, 0)

            # Gesamtzahl
            total = data.get("meta", {}).get("count", 0)
            print(f"  '{label}': {total} Works gefunden, {len(journal_counts)} unique Journals")

        except Exception as e:
            print(f"  Fehler: {e}")

    # Nur neue (nicht im Registry) UND mind. 2 Matches
    candidates = [c for c in seen.values()
                  if c["issn"].replace("-", "").upper() not in existing
                  and c["matched_works"] >= 2]

    # Sortieren: meisten Matches zuerst
    candidates.sort(key=lambda c: -c["matched_works"])

    print(f"  => {len(candidates)} neuer Kandidat(en) mit ≥2 Data-Paper-Werken")
    return candidates


def strategy_publisher_data_journals(existing):
    """
    Strategie 2 (Ergänzend):
    Bekannte Verlage mit Data-Journal-Programmen durchsuchen.
    """
    print("\n=== Strategie 2: Verlagsspezifische Suche ===")
    candidates = {}
    seen = set()

    # Ubiquity Press: bekannt für Open Data Journals
    try:
        r = requests.get(
            "https://api.openalex.org/sources",
            params={
                "filter": "publisher:Ubiquity+Press",
                "search": "data",
                "per_page": 25,
                "select": "id,display_name,issn,homepage_url",
            },
            headers={"User-Agent": UA}, timeout=20
        )
        if r.status_code == 200:
            for src in r.json().get("results", []):
                issn_list = src.get("issn") or []
                if not issn_list:
                    continue
                issn = issn_list[0]
                n = issn.replace("-", "").upper()
                if n in existing or n in seen:
                    continue
                seen.add(n)
                name = src.get("display_name", "")
                candidates[n] = {
                    "issn": issn,
                    "journal_title": name,
                    "publisher": "Ubiquity Press",
                    "url": src.get("homepage_url", "") or "",
                    "source": "publisher-ubiquity-press",
                    "evidence": f"Ubiquity-Press-Journal mit 'data' im Titel: {name}",
                }
        time.sleep(0.3)
    except Exception as e:
        print(f"  Fehler Ubiquity Press: {e}")

    # Pensoft: bekannt für Data Journals (Biodiversity Data Journal etc.)
    for pub in ["Pensoft Publishers", "Pensoft"]:
        try:
            r = requests.get(
                "https://api.openalex.org/sources",
                params={
                    "filter": f"publisher:{urllib.parse.quote(pub)}",
                    "search": "data",
                    "per_page": 25,
                    "select": "id,display_name,issn,homepage_url",
                },
                headers={"User-Agent": UA}, timeout=20
            )
            if r.status_code == 200:
                for src in r.json().get("results", []):
                    issn_list = src.get("issn") or []
                    if not issn_list:
                        continue
                    issn = issn_list[0]
                    n = issn.replace("-", "").upper()
                    if n in existing or n in seen:
                        continue
                    seen.add(n)
                    name = src.get("display_name", "")
                    candidates[n] = {
                        "issn": issn,
                        "journal_title": name,
                        "publisher": pub,
                        "url": src.get("homepage_url", "") or "",
                        "source": "publisher-pensoft",
                        "evidence": f"Pensoft-Journal mit 'data' im Titel: {name}",
                    }
            time.sleep(0.3)
        except Exception as e:
            print(f"  Fehler {pub}: {e}")

    # MDPI "Data" Journal und verwandte
    try:
        r = requests.get(
            "https://api.openalex.org/sources",
            params={
                "filter": "publisher:MDPI",
                "search": "data",
                "per_page": 25,
                "select": "id,display_name,issn,homepage_url",
            },
            headers={"User-Agent": UA}, timeout=20
        )
        if r.status_code == 200:
            for src in r.json().get("results", []):
                issn_list = src.get("issn") or []
                if not issn_list:
                    continue
                issn = issn_list[0]
                n = issn.replace("-", "").upper()
                if n in existing or n in seen:
                    continue
                seen.add(n)
                name = src.get("display_name", "")
                candidates[n] = {
                    "issn": issn,
                    "journal_title": name,
                    "publisher": "MDPI",
                    "url": src.get("homepage_url", "") or "",
                    "source": "publisher-mdpi",
                    "evidence": f"MDPI-Journal mit 'data' im Titel: {name}",
                }
        time.sleep(0.3)
    except Exception as e:
        print(f"  Fehler MDPI: {e}")

    print(f"  => {len(candidates)} neuer Kandidat(en) von Verlagen")
    return list(candidates.values())


def verify(candidates):
    """Verifiziere via OpenAlex und reichere Metadaten an."""
    print(f"\n=== Verifiziere {len(candidates)} Kandidaten ===")
    for c in candidates:
        issn = c["issn"]
        try:
            r = requests.get(
                f"https://api.openalex.org/sources?filter=issn:{issn}",
                headers={"User-Agent": UA}, timeout=15
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
            time.sleep(0.2)
        except Exception as e:
            c["verified"] = False
            c["verify_error"] = str(e)
    return candidates


def main():
    print("=" * 60)
    print("Data Journal Discovery")
    print(f"  Datum: {datetime.now().isoformat()}")
    print(f"  Methode: Data-Paper-Titel → Journal-Aggregation + Verlagsscan")
    print("=" * 60)

    existing = load_existing()
    print(f"  Bereits im Registry: {len(existing)} ISSNs")

    # Strategien
    titles = strategy_data_paper_titles(existing)
    publishers = strategy_publisher_data_journals(existing)

    # Merge
    merged = {}
    for c in titles + publishers:
        n = c["issn"].replace("-", "").upper()
        if n not in merged:
            merged[n] = c
        else:
            if c.get("matched_works", 0) > merged[n].get("matched_works", 0):
                merged[n]["matched_works"] = c.get("matched_works", 0)
            merged[n]["source"] = merged[n].get("source", "") + ", " + c.get("source", "")
            # Combine evidence
            existing_ev = merged[n].get("evidence", "")
            new_ev = c.get("evidence", "")
            if new_ev and new_ev not in existing_ev:
                merged[n]["evidence"] = existing_ev + " | " + new_ev if existing_ev else new_ev

    all_candidates = list(merged.values())

    # Verifiziere
    verified = verify(all_candidates)
    confirmed = [c for c in verified if c.get("verified")]
    unconfirmed = [c for c in verified if not c.get("verified")]

    # Sort: matched_works absteigend
    confirmed.sort(key=lambda c: -c.get("matched_works", 0))

    # Ausgabe
    result = {
        "generated": datetime.now().isoformat(),
        "existing_count": len(existing),
        "total_candidates": len(all_candidates),
        "confirmed_journals": len(confirmed),
        "unconfirmed": len(unconfirmed),
        "candidates": confirmed + unconfirmed,
        "methodology": (
            "1) OpenAlex-Works mit 'data paper'/'data descriptor' im Titel → "
            "nach Journal gruppiert → nur Journals mit ≥2 Treffern.\n"
            "2) Verlagsscan: Ubiquity Press, Pensoft, MDPI → Journals mit 'data' im Titel.\n\n"
            "ALLE Kandidaten brauchen manuelle Prüfung pro CONTRIBUTING.md!"
        ),
    }

    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=> {CANDIDATES_PATH}")

    # Top-Liste
    if confirmed:
        print(f"\n{'='*60}")
        print("TOP-KANDIDATEN (neue Journals, nicht im Registry):")
        print("=" * 60)
        for c in confirmed[:20]:
            mw = c.get("matched_works", 0)
            wc = c.get("works_count", 0) or 0
            print(f"  {c['issn']:<12} {c['journal_title'][:58]:<58}")
            print(f"  {'':>12} Verlag: {c.get('publisher','?'):<30} Works:{wc:<8}", end="")
            if mw:
                print(f" DataPaper:{mw}", end="")
            print()

    return 0


if __name__ == "__main__":
    main()
