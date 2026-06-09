#!/usr/bin/env python3
"""
Data Journal Discovery v4 — Citation Mining

Idee: Finde Papers, die bekannte Data-Journal-Übersichtsarbeiten zitieren.
Extrahiere ALLE referenzierten Journals aus diesen Papers.
Co-zitierte Journals, die oft mit Data Journals genannt werden,
sind wahrscheinlich selbst Data Journals.

Quellen:
- Candela et al. (2015) "Data journals: A survey" → W2104048833 (132 Zitationen)
- Li, Lu & Jiao (2021) "A Survey of Exclusively Data Journals" → ?
"""

import csv, json, os, sys, time
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

# Bekannte Data-Journal-Review-Artikel (OpenAlex IDs)
SEED_PAPERS = [
    "W2104048833",   # Candela et al. 2015 "Data journals: A survey" (132 cit)
    "W4387950141",   # Jiao et al. 2023 "How are exclusively data journals indexed" (33 cit)
    "W3206639999",   # Li, Lu & Jiao 2021 "A Survey of Exclusively Data Journals" (1 cit)
]


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


def get_work_ids_via_citation(seed_id):
    """Find works that CITE a seed paper, return their referenced_works."""
    print(f"  Hole Zitationen von {seed_id}...")
    all_refs = set()
    cursor = "*"
    page = 0

    while cursor and page < 5:  # max 5 Seiten
        try:
            url = f"https://api.openalex.org/works?filter=cites:{seed_id}&per_page=200&cursor={cursor}&select=referenced_works,primary_location,type"
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            meta = data.get("meta", {})
            cursor = meta.get("next_cursor")
            page += 1

            for w in data.get("results", []):
                for ref in w.get("referenced_works", []):
                    all_refs.add(ref)

            time.sleep(0.3)
        except Exception as e:
            print(f"    Fehler: {e}")
            break

    print(f"    => {len(all_refs)} unique referenzierte Works")
    return list(all_refs)


def resolve_to_journals(work_ids, existing, batch_size=50):
    """
    Resolve a list of OpenAlex work IDs to their source journals.
    Returns dict: normalized_issn → {name, count}
    """
    journal_counts = {}

    for i in range(0, len(work_ids), batch_size):
        batch = work_ids[i:i+batch_size]
        # Extract short IDs (last part after /)
        short_ids = []
        for wid in batch:
            if wid.startswith("http"):
                wid = wid.rsplit("/", 1)[-1]
            short_ids.append(wid)
        ids_param = "|".join(short_ids)

        try:
            r = requests.get(
                f"https://api.openalex.org/works?filter=openalex_id:{ids_param}&per_page={batch_size}&select=primary_location,type,cited_by_count",
                headers={"User-Agent": UA},
                timeout=30,
            )
            if r.status_code == 200:
                for w in r.json().get("results", []):
                    if w.get("type") != "article":
                        continue
                    loc = w.get("primary_location") or {}
                    src = loc.get("source") or {}
                    if src.get("type") != "journal":
                        continue
                    issn_list = src.get("issn") or []
                    if not issn_list:
                        continue
                    issn = issn_list[0]
                    name = src.get("display_name", "?")
                    n_issn = issn.replace("-", "").upper()

                    if n_issn not in journal_counts:
                        journal_counts[n_issn] = {
                            "issn": issn,
                            "name": name,
                            "count": 0,
                            "publisher": src.get("host_organization_name", "") or "?",
                            "url": src.get("homepage_url", "") or "",
                        }
                    journal_counts[n_issn]["count"] += 1

            time.sleep(0.3)
        except Exception as e:
            print(f"    Batch-Fehler: {e}")

    return journal_counts


def main():
    print("=" * 60)
    print(f"Data Journal Discovery v4 — Citation Mining")
    print(f"  Datum: {datetime.now().isoformat()}")
    print("=" * 60)

    existing = load_existing()
    print(f"  Bereits im Registry: {len(existing)} ISSNs")

    all_journals = {}

    for seed in SEED_PAPERS:
        # 1. Get citing works → their references
        ref_ids = get_work_ids_via_citation(seed)

        if not ref_ids:
            print(f"  Überspringe {seed} (keine Daten)")
            continue

        # 2. Resolve references to journals
        journals = resolve_to_journals(ref_ids, existing)
        print(f"  => {len(journals)} unique Journals in den Referenzen")

        # Merge
        for n_issn, j in journals.items():
            if n_issn not in all_journals:
                all_journals[n_issn] = j
            else:
                all_journals[n_issn]["count"] += j["count"]

    # Filtern: Nur Journals NICHT im Registry UND ≥2x zitiert
    candidates = []
    for n_issn, j in sorted(all_journals.items(), key=lambda x: -x[1]["count"]):
        if n_issn in existing:
            continue
        if j["count"] < 2:
            continue
        candidates.append({
            "issn": j["issn"],
            "journal_title": j["name"],
            "publisher": j["publisher"],
            "url": j["url"],
            "source": "citation-mining",
            "evidence": f"Zitiert in {j['count']} Papers, die Data-Journal-Reviews zitieren",
            "co_citations": j["count"],
        })

    print(f"\n=== ERGEBNIS: {len(candidates)} Kandidaten (≥2 Co-Zitationen) ===")

    # Ausgabe
    result = {
        "generated": datetime.now().isoformat(),
        "existing_count": len(existing),
        "total_candidates": len(candidates),
        "candidates": candidates,
        "methodology": (
            "Citation Mining: Papers, die Candela et al. (2015) und Jiao et al. (2023) zitieren, "
            "wurden analysiert. Alle referenzierten Journals wurden extrahiert und nach "
            "Häufigkeit sortiert. Journals mit ≥2 Nennungen, die nicht im Registry sind, "
            "sind Kandidaten. Diese müssen manuell geprüft werden."
        ),
    }

    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nGespeichert: {CANDIDATES_PATH}")
    print(f"\nTOP 20 KANDIDATEN:")
    print("-" * 80)
    for c in candidates[:20]:
        print(f"  {c['co_citations']:>3}x {c['issn']:<12} {c['journal_title'][:60]}")
        print(f"  {'':>15} Verlag: {c.get('publisher','?'):<40}")
        print()

    return 0


if __name__ == "__main__":
    main()
