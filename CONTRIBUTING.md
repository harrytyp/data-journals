# Contributing to the Data Journal Registry

## Scope & Definitions

This registry is based on the methodology of [Kindling & Strecker (2022)](https://doi.org/10.5281/zenodo.7082126), developed within the [re3data COREF](https://www.re3data.org/) project. The original dataset was compiled by aggregating existing sources (Candela et al. 2015, Li et al. 2021, Callaghan 2013, et al.) and is supplemented by community contributions.

### Core Definition

> *"Data journals focus on the publication of **data papers** — a specialized publication type describing datasets, their collection and reuse potential that is peer-reviewed, citable and indexed."*
>
> — Kindling & Strecker (2022), Zenodo

A **data paper** is a scholarly publication whose primary purpose is to describe a dataset (or collection of datasets), including its provenance, collection methods, technical validation, and reuse potential — rather than to present new hypotheses, analyses, or interpretations.

### Inclusion Criteria

A journal qualifies for this registry if it meets **all** of the following criteria:

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | **Peer-reviewed** scholarly journal | Has ISSN; articles undergo peer review |
| 2 | **Data paper as an explicit publication format** | Journal offers "Data Paper", "Data Descriptor", "Data Article", "Data Note", or equivalent as a defined article type in its author guidelines |
| 3 | **Peer review applies to data papers** | Data papers are reviewed (not merely deposited); quality checks documented |
| 4 | **Citable** | Data papers receive a persistent identifier (DOI, handle, or similar) and are indexed |

### Exclusion Criteria

The following are **not** included:

- **Research data repositories** (e.g., Zenodo, figshare, Dryad) — no journal structure, no peer review
- **Preprint servers** — no peer review
- **Conference proceedings** — not a journal
- **Blogs or magazines** — no ISSN, no peer review
- **Journals without an explicit data paper format** — even if they occasionally publish data-related articles
- **Data sections in non-data journals** — unless the section is a named, peer-reviewed article type

### Classification: Pure vs. Mixed

| Type | Definition | Examples |
|------|------------|----------|
| **Pure** | Journal has a **strong focus** on publishing data papers; data papers are the primary or exclusive article type. Typically: journal title contains "Data Journal" or >70% of published articles are data papers. | *Data in Brief*, *Earth System Science Data*, *Journal of Open Humanities Data*, *JoDaKISS* |
| **Mixed** | Journal publishes data papers **alongside** other publication types (research articles, reviews, methods, etc.). Data papers are one format among many. | *Scientific Data*, *GigaScience*, *Biodiversity Data Journal*, *F1000Research* |

### Metadata Fields

| Field | Description | Source |
|-------|-------------|--------|
| `ISSN` | International Standard Serial Number (print or electronic) | Manually verified |
| `journal_title` | Title of the journal (as registered with ISSN) | Crossref (initial), manually updated |
| `publisher` | Publisher name | Crossref (initial), harmonized |
| `URL` | Journal homepage URL | Manually added |
| `data_journal_type` | Classification: `pure` or `mixed` | Manually assigned based on journal scope |

### Sources

The initial list was compiled from these sources (curated in [Zotero](https://www.zotero.org/groups/2316312/oabb/collections/MVSCZTBL)):

| Source | Type | Year |
|--------|------|------|
| Candela, Castelli & Manghi — *Data journals: A survey* | Academic survey | 2015 |
| Li, Lu & Jiao — *A Survey of Exclusively Data Journals* | Academic survey | 2021 |
| Callaghan — *A list of Data Journals (in no particular order)* (PREPARDE) | Community list | 2013 |
| *A Growing List of Data Journals* (University of Michigan) | Blog | 2014 |
| *Data Journal Directory* (Finnish Committee for Research Data) | Directory | 2020 |
| García-García et al. — *Data journals: eclosión de nuevas revistas* | Academic survey | 2015 |
| Schöpfel et al. — *Data papers as a new form of knowledge organization* | Conference paper | 2019 |

---

## How to Add a Journal

### Via Pull Request

1. **Research the journal** — verify ISSN, homepage URL, author guidelines
2. **Check the criteria** — does it have a named "Data Paper" format?
3. **Determine the type**:
   - **Pure**: Data papers are the core offering; other formats are rare or absent
   - **Mixed**: Data papers exist alongside research articles, reviews, etc.
4. **Add to `data_journals_characteristics.csv`** — append a new row with all fields
5. **Update `data/journals.json`** — run `scripts/convert_csv_to_json.py`
6. **Open a Pull Request**

### CSV Format

```csv
ISSN,journal_title,publisher,URL,data_journal_type
1234-5678,Journal Name,Publisher Name,https://example.org/,pure
```

**Important:** Keep the CSV in the same order as the original (alphabetical by journal title is preferred). No empty ISSN rows. No duplicate entries.

### Classification Guidelines

Ask these questions to determine `pure` vs `mixed`:

- **What is the journal's name?** If it contains "Data Journal", "Data Papers", or "Data Brief", it's likely **pure**.
- **What does the "About" page say?** If the journal exclusively or primarily publishes data papers, it's **pure**. If it says "welcomes data papers, research articles, and reviews", it's **mixed**.
- **What article types are listed in the author guidelines?** If "Data Paper" is the only type or the flagship type, it's **pure**. If it's one among many, it's **mixed**.

---

## Automated Discovery

This repository includes a script for suggesting candidate data journals not yet in the registry.

### `scripts/discover_candidates.py`

The script uses two strategies:

**Strategie 1 (Primär): Data-Paper-Titel → Journal-Aggregation**
Findet Publikationen in OpenAlex, deren Titel Begriffe wie "Data Paper" oder "Data Note" enthalten — das sind typische Titel von Data-Paper-Artikeln. Diese werden nach Journal-ISSN gruppiert. Journals, die regelmäßig solche Artikel veröffentlichen, sind wahrscheinlich Data Journals.

*Ergebnis:* Derzeit ~4.300 "Data Paper"-Works, gruppiert in ~109 Journals. Davon ca. 30 nicht im Registry.

**Strategie 2 (Ergänzend): Verlagsscan**
Durchsucht bekannte Data-Journal-Verlage (Ubiquity Press, Pensoft, MDPI) nach Journals mit "Data" im Titel.

### Wichtige Einschränkung

Eine rein automatische Erkennung von Data Journals ist nicht zuverlässig möglich, weil:
- Es keine standardisierte Metadaten-Kennzeichnung für "Data Journal" gibt
- Crossref/OpenAlex keinen spezifischen "data-paper"-Publikationstyp haben
- Begriffe wie "Data Descriptor" in der Chemie eine andere Bedeutung haben (Moleküldeskriptoren)

Die beste Methode bleibt: **Automatische Vorauswahl → menschliche Prüfung.**

### Regelmäßiger Lauf

Ein GitHub Actions Workflow läuft wöchentlich und erstellt ein Issue mit Kandidaten.

### Manuelle Prüfung

So prüfst du einen Kandidaten:
1. Rufe die Journal-Homepage auf
2. Suche in den Author Guidelines nach "Data Paper", "Data Note", "Data Descriptor" als Artikeltyp
3. Prüfe, ob Data Papers peer-reviewed und zitierfähig sind
4. Füge bei Erfüllung aller Kriterien via PR hinzu

---

## Workflow

1. **Automated discovery** → candidates list
2. **Manual verification** — check criteria (ISSN, author guidelines, peer review)
3. **Add to CSV** if verified
4. **Deploy** via GitHub Pages

---

## License

This dataset is licensed under [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).
