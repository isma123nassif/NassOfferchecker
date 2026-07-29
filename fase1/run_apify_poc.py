import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ACTOR_PROFILES = {
    "abotapi": {
        "actor_id": "abotapi~leroymerlin-es-scraper",
        "batch": False,
    },
    "studio-amba-es": {
        "actor_id": "studio-amba~leroymerlin-es-scraper",
        "batch": False,
    },
    "sian-fr": {
        "actor_id": "sian.agency~leroy-merlin-product-scraper",
        "batch": True,
    },
    "studio-amba-fr": {
        "actor_id": "studio-amba~leroymerlin-scraper",
        "batch": False,
    },
}


def read_eans(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if reader.fieldnames and "ean" in reader.fieldnames:
            return [row["ean"].strip() for row in reader if row.get("ean", "").strip()]

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "ean" in reader.fieldnames:
            return [row["ean"].strip() for row in reader if row.get("ean", "").strip()]

    raise ValueError(f"No ean column found in {path}")


def post_json(url: str, token: str, payload: dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify HTTP {exc.code}: {body}") from exc


def actor_input(actor: str, eans: list[str], max_results: int) -> dict[str, Any]:
    if actor == "abotapi":
        if len(eans) != 1:
            raise ValueError("abotapi profile must be run one EAN at a time")
        return {
            "mode": "search",
            "searchTerm": eans[0],
            "sortBy": "relevance",
            "sellerFilter": "any",
            "fetchDetails": True,
            "fetchReviews": False,
            "maxItems": max_results,
            "proxy": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": "ES",
            },
        }

    if actor == "studio-amba-es":
        if len(eans) != 1:
            raise ValueError("studio-amba-es profile must be run one EAN at a time")
        payload: dict[str, Any] = {
            "searchQuery": eans[0],
            "maxResults": max_results,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": "ES",
            },
        }
        bright_data_key = os.environ.get("BRIGHTDATA_API_KEY")
        if bright_data_key:
            payload["brightDataApiKey"] = bright_data_key
        return payload

    if actor == "sian-fr":
        return {
            "keywords": eans,
            "scrapeMode": "detail",
            "sort": "relevance",
            "maxResults": max_results,
        }

    if actor == "studio-amba-fr":
        if len(eans) != 1:
            raise ValueError("studio-amba-fr profile must be run one EAN at a time")
        return {
            "searchQuery": eans[0],
            "maxResults": max_results,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
            },
        }

    raise ValueError(f"Unknown actor profile: {actor}")


def find_first(item: dict[str, Any], keys: list[str]) -> Any:
    lowered = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, ""):
            return lowered[key.lower()]
    return ""


def item_mentions_ean(item: Any, ean: str) -> bool:
    return ean in json.dumps(item, ensure_ascii=False)


def summarize(eans: list[str], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for ean in eans:
        matches = [item for item in items if item_mentions_ean(item, ean)]
        best = matches[0] if matches else {}
        status = "VIVA_CANDIDATA" if matches else "NO_ENCONTRADA"

        if not items:
            status = "INCIERTA"

        rows.append(
            {
                "ean": ean,
                "preliminary_status": status,
                "matched_items": len(matches),
                "total_items_returned": len(items),
                "title": find_first(best, ["productTitle", "title", "name"]),
                "url": find_first(best, ["url", "productUrl", "product_url"]),
                "gtin": find_first(best, ["gtin", "ean", "barcode"]),
                "sku": find_first(best, ["sku", "item_id", "itemId"]),
                "price": find_first(best, ["price", "currentPrice", "priceText"]),
                "seller": find_first(best, ["seller_name", "sellerName", "seller"]),
                "availability": find_first(best, ["availability", "stock", "inStock"]),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor", choices=ACTOR_PROFILES.keys(), required=True)
    parser.add_argument("--ean-file", type=Path, default=Path("fase1/eans_poc.csv"))
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("Missing APIFY_TOKEN environment variable", file=sys.stderr)
        return 2

    eans = read_eans(args.ean_file)
    profile = ACTOR_PROFILES[args.actor]
    actor_id = profile["actor_id"]
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    all_items: list[dict[str, Any]] = []
    raw_payloads: list[Any] = []

    if profile["batch"]:
        payload = actor_input(args.actor, eans, args.max_results)
        result = post_json(url, token, payload, args.timeout)
        raw_payloads.append(result)
        all_items.extend(result if isinstance(result, list) else [])
    else:
        for ean in eans:
            payload = actor_input(args.actor, [ean], args.max_results)
            try:
                result = post_json(url, token, payload, args.timeout)
                raw_payloads.append({"ean": ean, "input": payload, "result": result})
                if isinstance(result, list):
                    all_items.extend(result)
            except Exception as exc:
                raw_payloads.append({"ean": ean, "input": payload, "error": str(exc)})
            time.sleep(2)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("fase1/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / f"{timestamp}_{args.actor}_raw.json"
    raw_path.write_text(json.dumps(raw_payloads, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_rows = summarize(eans, all_items)
    summary_path = output_dir / f"{timestamp}_{args.actor}_summary.csv"
    write_csv(summary_path, summary_rows)

    print(f"Raw output: {raw_path}")
    print(f"Summary: {summary_path}")
    print(json.dumps(summary_rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
