import json
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


EAN = "8436616281243"
SELLER_URL = (
    "https://www.worten.pt/search?query=*&facetFilters=seller_id:"
    "e5dae97c-401c-456a-be59-56a4f73b0bb5&utm_source=sellerpage_redirect"
)
BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "fase1" / "worten_probe"
PROFILE_DIR = BASE_DIR / "fase1" / "edge_manual_worten_probe"
PORT = 9341


def find_edge() -> str:
    path = shutil.which("msedge.exe") or shutil.which("msedge")
    if path:
        return path
    for candidate in (
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("No encuentro Microsoft Edge")


def visible_challenge(text: str, title: str) -> bool:
    data = f"{title}\n{text}".casefold()
    markers = (
        "executando verificacao de seguranca",
        "executando verificação de segurança",
        "confirme que e humano",
        "confirme que é humano",
        "checking your browser",
        "verify you are human",
        "um momento",
    )
    return any(marker in data for marker in markers)


def wait_manual_ready(page, timeout_seconds: int = 600) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=5000)
            title = page.title()
        except Exception:
            text = ""
            title = ""
        if not visible_challenge(text, title):
            return
        print("CHALLENGE_VISIBLE: resuelvelo en Edge; espero...")
        page.wait_for_timeout(3000)
    raise TimeoutError("Challenge no resuelto dentro del timeout")


def find_search_input(page):
    selectors = [
        "input[type='search']",
        "input[name='query']",
        "input[name='q']",
        "input[placeholder*='Procurar']",
        "input[placeholder*='Pesquisar']",
        "input[placeholder*='Search']",
        "[data-testid*='search'] input",
        "#search-input",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=5000)
            return locator
        except Exception:
            continue
    raise RuntimeError("No encuentro el cuadro de busqueda")


def wait_results(page, ean: str, timeout_seconds: int = 25) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_text = ""
    while time.monotonic() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=5000)
            html = page.content()
            title = page.title()
        except Exception:
            text = ""
            html = ""
            title = ""
        last_text = text
        lower = text.casefold()
        if visible_challenge(text, title):
            wait_manual_ready(page)
            continue
        if ean in html or "vendido por" in lower or "mark jv shop" in lower or "sem resultados" in lower or "nenhum resultado" in lower:
            return html
        page.wait_for_timeout(1000)
    return page.content() if page else last_text


def extract_cards(page, ean: str) -> list[dict]:
    script = """
    (ean) => {
      const cards = Array.from(document.querySelectorAll('article, [data-testid*="product"], [class*="product"], [class*="card"]'));
      const picked = [];
      for (const el of cards) {
        const txt = (el.innerText || '').trim();
        const html = el.innerHTML || '';
        if (!txt) continue;
        if (!(txt.toLowerCase().includes('vendido por') || html.includes(ean) || txt.includes(ean))) continue;
        const link = el.querySelector('a[href]');
        const img = el.querySelector('img[alt]');
        const priceMatch = txt.match(/\\d+[,.]\\d{2}\\s*€/) || txt.match(/€\\s*\\d+[,.]\\d{2}/);
        const sellerMatch = txt.match(/Vendido por\\s+([^\\n]+)/i);
        picked.push({
          title: img?.getAttribute('alt') || (txt.split('\\n').find(x => x.length > 8 && !x.includes('€')) || ''),
          price: priceMatch ? priceMatch[0] : '',
          seller: sellerMatch ? sellerMatch[1].trim() : '',
          url: link ? new URL(link.getAttribute('href'), location.href).href : '',
          text: txt.slice(0, 800)
        });
      }
      return picked.slice(0, 10);
    }
    """
    return page.evaluate(script, ean)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    edge = find_edge()
    args = [
        edge,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        SELLER_URL,
    ]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = {"ean": EAN, "status": "started", "cards": []}
    try:
        with sync_playwright() as p:
            browser = None
            endpoint = f"http://127.0.0.1:{PORT}"
            deadline = time.monotonic() + 30
            last_error = None
            while time.monotonic() < deadline:
                try:
                    browser = p.chromium.connect_over_cdp(endpoint, timeout=5000)
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(1)
            if browser is None:
                raise RuntimeError(f"No puedo conectar por CDP: {last_error}")
            context = browser.contexts[0]
            page = context.pages[-1] if context.pages else context.new_page()
            page.set_default_timeout(15000)
            try:
                page.goto(SELLER_URL, wait_until="domcontentloaded", timeout=20000)
            except PlaywrightTimeoutError:
                pass
            wait_manual_ready(page)
            search = find_search_input(page)
            search.click()
            search.fill("")
            search.fill(EAN)
            page.keyboard.press("Enter")
            html = wait_results(page, EAN)
            cards = extract_cards(page, EAN)
            html_path = OUT_DIR / f"{EAN}.html"
            html_path.write_text(html, encoding="utf-8")
            result.update(
                {
                    "status": "ok" if cards else "no_card_extracted",
                    "final_url": page.url,
                    "title": page.title(),
                    "cards": cards,
                    "html_path": str(html_path),
                }
            )
            browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
    out_path = OUT_DIR / f"{EAN}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
