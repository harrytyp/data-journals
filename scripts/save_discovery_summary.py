#!/usr/bin/env python3
"""Read data/candidates.json and write data/discovery_summary.md."""
import json
import sys
from pathlib import Path

data_path = Path("data/candidates.json")
if not data_path.exists():
    print("No candidates.json found, nothing to summarize.")
    sys.exit(0)

d = json.loads(data_path.read_text())

generated = d.get("generated", "unknown")
verified_count = d.get("verified_candidates", 0)
unverified_count = d.get("unverified_candidates", 0)

lines = []
lines.append("## 🔍 Data Journal Discovery Results")
lines.append("")
lines.append(f"Generated: {generated}")
lines.append("")
lines.append(f"### Verified Candidates ({verified_count})")
lines.append("")
lines.append("| ISSN | Title | Publisher | Source |")
lines.append("|------|-------|-----------|--------|")

for c in d.get("candidates", []):
    if c.get("verified"):
        issn = c.get("issn", "?")
        title = c.get("journal_title", "?")
        publisher = c.get("publisher", "?")
        source = c.get("source", "?")
        lines.append(f"| {issn} | {title} | {publisher} | {source} |")

if unverified_count > 0:
    lines.append("")
    lines.append(f"### Unverified Candidates ({unverified_count})")
    lines.append("")
    lines.append("These require manual ISSN lookup before they can be verified.")

lines.append("")
lines.append("---")
lines.append("")
lines.append("_Run `python scripts/discover_candidates.py` locally for full details._")
lines.append("_All candidates require manual verification per the CONTRIBUTING.md criteria._")

body = "\n".join(lines) + "\n"
Path("data/discovery_summary.md").write_text(body)
print(f"Written data/discovery_summary.md ({len(body)} chars)")
