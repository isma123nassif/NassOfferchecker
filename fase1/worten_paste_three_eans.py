import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = BASE_DIR / "fase1" / "worten_probe" / "worker_state.json"
OUT_DIR = BASE_DIR / "fase1" / "worten_probe"
EANS = ["8436616281243", "8436579953188", "8436579953102"]


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
            locator.wait_for(state="visible", timeout=2500)
            return locator
        except Exception:
            continue
    raise RuntimeError("No encuentro el cuadro de busqueda visible")


def main() -> None:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    endpoint = state["cdp_endpoint"]
    query = " ".join(EANS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {"status": "started", "endpoint": endpoint, "eans": EANS}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint, timeout=10000)
        context = browser.contexts[0]
        page = context.pages[-1] if context.pages else context.new_page()
        page.set_default_timeout(10000)
        search = find_search_input(page)
        search.click()
        search.fill("")
        search.fill(query)
        page.keyboard.press("Enter")
        page.wait_for_timeout(8000)
        html = page.content()
        text = page.locator("body").inner_text(timeout=5000)
        html_path = OUT_DIR / "worten_three_eans_after_search.html"
        html_path.write_text(html, encoding="utf-8")
        result.update(
            {
                "status": "submitted",
                "url": page.url,
                "title": page.title(),
                "contains": {ean: ean in html or ean in text for ean in EANS},
                "seller_seen": "MARK JV" in text.upper() or "MARK JV" in html.upper(),
                "html_path": str(html_path),
            }
        )
        # Keep the worker/browser open for manual inspection.
    (OUT_DIR / "worten_three_eans_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
