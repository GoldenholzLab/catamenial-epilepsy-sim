#!/usr/bin/env python3
"""Verify the hormone-simulator citation registry against PubMed metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.literature import CITATIONS  # noqa: E402

PUBMED_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def normalize_title(value: str) -> str:
    """Normalize punctuation, markup, and case for robust title comparison."""

    value = unicodedata.normalize("NFKD", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&amp;", " and ").replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def normalized_doi(value: str) -> str:
    """Normalize DOI case and URL prefixes."""

    return value.casefold().removeprefix("https://doi.org/").rstrip(".")


def fetch_pubmed(pmids: list[str]) -> Dict[str, dict]:
    """Fetch PubMed summaries for all registry PMIDs in one request."""

    query = urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
    request = Request(
        f"{PUBMED_ESUMMARY}?{query}",
        headers={"User-Agent": "hormone-cycler-citation-audit/0.2.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload["result"]


def audit_registry() -> dict:
    """Return a machine-readable citation audit report."""

    pmids = [citation.pmid for citation in CITATIONS.values() if citation.pmid]
    pubmed = fetch_pubmed(pmids)
    records = []
    for key, citation in CITATIONS.items():
        problems = []
        metadata = pubmed.get(citation.pmid) if citation.pmid else None
        if citation.pmid and metadata is None:
            problems.append("PMID not returned by PubMed")
        if metadata is not None:
            observed_title = metadata.get("title", "")
            if normalize_title(observed_title) != normalize_title(citation.title):
                problems.append(
                    f"title mismatch: PubMed={observed_title!r}; registry={citation.title!r}"
                )
            observed_doi = next(
                (
                    item.get("value", "")
                    for item in metadata.get("articleids", [])
                    if item.get("idtype") == "doi"
                ),
                "",
            )
            if citation.doi and normalized_doi(observed_doi) != normalized_doi(citation.doi):
                problems.append(
                    f"DOI mismatch: PubMed={observed_doi!r}; registry={citation.doi!r}"
                )
        if citation.pmid and f"/{citation.pmid}/" not in citation.url:
            problems.append("registry URL does not contain its PMID")
        if not citation.evidence_role:
            problems.append("missing evidence role")
        records.append(
            {
                "key": key,
                "pmid": citation.pmid,
                "doi": citation.doi,
                "title": citation.title,
                "evidence_role": citation.evidence_role,
                "passed": not problems,
                "problems": problems,
            }
        )
    return {
        "registry_size": len(records),
        "pubmed_records": len(pmids),
        "passed": all(record["passed"] for record in records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = audit_registry()
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
