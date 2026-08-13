#!/usr/bin/env python3
"""Export the Paper 1 Zotero bibliography from the CERES collection."""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "zotero_references.json"
DEFAULT_COLLECTION_KEY = "SNEPUMQA"
DEFAULT_STYLE = "american-medical-association"

REFERENCE_TITLES = [
    "Frequency of catamenial seizure exacerbation in women with localization-related epilepsy",
    "Three patterns of catamenial epilepsy",
    "Patterns of seizure occurrence in catamenial epilepsy",
    "Catamenial epilepsy: definition, prevalence pathophysiology and treatment",
    "Catamenial epilepsy: Update on prevalence, pathophysiology and treatment from the findings of the NIH Progesterone Treatment Trial",
    "Treatments for seizures in catamenial (menstrual-related) epilepsy",
    "Progesterone vs placebo therapy for women with epilepsy: A randomized clinical trial",
    "The role of neurosteroids in the pathophysiology and treatment of catamenial epilepsy",
    "Multi-day rhythms modulate seizure risk in epilepsy",
    "Cycles in epilepsy",
    "Forecasting cycles of seizure likelihood",
    "Flexible realistic simulation of seizure occurrence recapitulating statistical properties of seizure diaries",
    "Menstrual cycle length variation by demographic characteristics from the Apple Women's Health Study",
    "Real-world menstrual cycle characteristics of more than 600,000 menstrual cycles",
    "Establishment of detailed reference values for luteinizing hormone, follicle stimulating hormone, estradiol, and progesterone during different phases of the menstrual cycle on the Abbott ARCHITECT analyzer",
    "Strengthening the reporting of empirical simulation studies: introducing the STRESS guidelines",
    "Catamenial epilepsy: a review",
    "How common is catamenial epilepsy?",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-key", default=DEFAULT_COLLECTION_KEY)
    parser.add_argument("--style", default=DEFAULT_STYLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    items = collection_items(args.collection_key)
    key_by_title = {normalize(item["data"].get("title", "")): item["key"] for item in items}
    ordered_keys = []
    missing = []
    for title in REFERENCE_TITLES:
        key = key_by_title.get(normalize(title))
        if key is None:
            missing.append(title)
        else:
            ordered_keys.append(key)
    if missing:
        joined = "\n".join(f"- {title}" for title in missing)
        raise SystemExit(f"Missing expected Zotero references in collection {args.collection_key}:\n{joined}")

    refs = [render_reference(key, args.style) for key in ordered_keys]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "source": "Zotero local API",
                "collection_key": args.collection_key,
                "style": args.style,
                "item_keys": ordered_keys,
                "references": refs,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


def zotero_get(path: str, params: dict[str, str]) -> object:
    url = "http://127.0.0.1:23119/api/users/0" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Zotero-API-Version": "3"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def collection_items(collection_key: str) -> list[dict[str, object]]:
    return zotero_get(
        f"/collections/{collection_key}/items/top",
        {"format": "json", "include": "data", "limit": "100"},
    )


def render_reference(item_key: str, style: str) -> str:
    data = zotero_get(
        "/items",
        {"itemKey": item_key, "include": "bib", "style": style},
    )
    bib = data[0]["bib"]
    match = re.search(r'<div class="csl-right-inline"[^>]*>(.*?)</div>', bib, flags=re.S)
    segment = match.group(1) if match else bib
    text = re.sub(r"<[^>]+>", "", segment)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


if __name__ == "__main__":
    raise SystemExit(main())
