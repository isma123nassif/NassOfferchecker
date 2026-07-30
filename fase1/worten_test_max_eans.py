import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent.parent
PROBE_DIR = BASE_DIR / "fase1" / "worten_probe"
STATE_PATH = PROBE_DIR / "worker_state.json"
FEED_PATH = PROBE_DIR / "worten_feed.csv"
SELLER_URL = (
    "https://www.worten.pt/search?query=*&facetFilters=seller_id:"
    "e5dae97c-401c-456a-be59-56a4f73b0bb5&utm_source=sellerpage_redirect"
)
COUNTS_TO_TEST = [40, 50, 75, 100, 150, 200]


def load_eans(limit: int) -> list[str]:
    eans: list[str] = []
    with FEED_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            ean = (row.get("ean") or "").strip()
            quantity_text = (row.get("quantity") or "0").strip()
            try:
                quantity = int(float(quantity_text.replace(",", ".")))
            except ValueError:
                quantity = 0
            if re.fullmatch(r"\d{8,14}", ean) and quantity > 0:
                eans.append(ean)
                if len(eans) >= limit:
                    break
    if len(eans) < limit:
        raise RuntimeError(f"Solo he encontrado {len(eans)} EAN con stock en el feed")
    return eans


def find_search_input(page):
    selectors = [
        "input[type='search']",
        "input[name='query']",
        "input[name='q']",
        "input[placeholder*='Pesquisa']",
        "input[placeholder*='Procurar']",
        "input[placeholder*='Pesquisar']",
        "[data-testid*='search'] input",
        "#search-input",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=4000)
            return locator
        except Exception:
            continue
    raise RuntimeError("No encuentro el cuadro de busqueda visible")


def wait_search_settled(page, requested: list[str], timeout_seconds: int = 18) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            html = page.content()
            text = page.locator("body").inner_text(timeout=4000)
        except Exception:
            page.wait_for_timeout(750)
            continue
        if "Resultados de pesquisa" in text or "produtos" in text or any(ean in html for ean in requested):
            return
        page.wait_for_timeout(750)


def query_eans_from_url(url: str) -> list[str]:
    query = parse_qs(urlparse(url).query).get("query", [""])[0]
    return re.findall(r"\d{8,14}", query)


def read_input_value(page) -> str:
    try:
        return page.evaluate(
            """
            () => {
              const el = document.querySelector(
                "input[type='search'], input[name='query'], input[name='q'], #search-input"
              );
              return el ? el.value : "";
            }
            """
        )
    except Exception:
        return ""


def run_one(page, eans: list[str]) -> dict:
    page.goto(SELLER_URL, wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(5000)
    search = find_search_input(page)
    query = " ".join(eans)
    search.click()
    search.fill("")
    search.fill(query)
    page.keyboard.press("Enter")
    wait_search_settled(page, eans)
    page.wait_for_timeout(2500)

    html = page.content()
    text = page.locator("body").inner_text(timeout=5000)
    url_eans = query_eans_from_url(page.url)
    input_value = read_input_value(page)
    input_eans = re.findall(r"\d{8,14}", input_value)
    found_eans = [ean for ean in eans if ean in html or ean in text]
    cards_with_seller = len(re.findall(r"Vendido por\s+MARK JV", text, flags=re.IGNORECASE))
    return {
        "requested": len(eans),
        "url_eans": len(url_eans),
        "input_eans": len(input_eans),
        "found_eans": len(found_eans),
        "seller_seen": "MARK JV" in text.upper() or "MARK JV" in html.upper(),
        "cards_with_seller": cards_with_seller,
        "final_url": page.url,
        "missing_from_url": [ean for ean in eans if ean not in url_eans],
        "missing_from_html": [ean for ean in eans if ean not in found_eans],
    }


def main() -> None:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    eans = load_eans(max(COUNTS_TO_TEST))
    results = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(state["cdp_endpoint"], timeout=10000)
        context = browser.contexts[0]
        page = context.pages[-1] if context.pages else context.new_page()
        page.set_default_timeout(15000)
        for count in COUNTS_TO_TEST:
            result = run_one(page, eans[:count])
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))

    output = {
        "status": "ok",
        "counts_tested": COUNTS_TO_TEST,
        "eans_used": eans,
        "results": results,
    }
    out_path = PROBE_DIR / "worten_max_eans_result.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
