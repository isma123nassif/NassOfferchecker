import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from html import unescape
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_SEARCH_URL = "https://www.leroymerlin.es/search?q={ean}"
HOME_URL = "https://www.leroymerlin.es/"
PROFILE_DIR = Path("fase1/browser_profile_leroy")
OUTPUT_ROOT = Path("fase1/output_playwright")


@dataclass
class BrowserCheckResult:
    ean: str
    status: str
    final_url: str
    title: str
    html_path: str
    screenshot_path: str
    cookies_path: str
    html_bytes: int
    ean_in_html: bool
    product_availability: str
    offer_available: bool
    availability_evidence: str
    candidate_count: int
    first_candidate_url: str
    challenge_detected: bool
    reason: str


def read_eans(path: Path) -> list[str]:
    for delimiter in (";", ","):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            if reader.fieldnames and "ean" in reader.fieldnames:
                return [row["ean"].strip() for row in reader if row.get("ean", "").strip()]
    raise ValueError(f"No ean column found in {path}")


def extract_candidate_urls(content: str) -> list[str]:
    patterns = [
        r"https://www\.leroymerlin\.es/productos/[^\"'<>\\\s]+?\.html",
        r"/productos/[^\"'<>\\\s]+?\.html",
    ]
    candidates = []
    seen = set()
    for pattern in patterns:
        for match in re.findall(pattern, content):
            url = match
            if url.startswith("/"):
                url = "https://www.leroymerlin.es" + url
            url = url.split("?")[0]
            if url not in seen:
                seen.add(url)
                candidates.append(url)
    return candidates


def challenge_detected(content: str, title: str, url: str) -> bool:
    lowered = f"{title}\n{url}\n{content[:200000]}".lower()
    has_usable_page = (
        len(content.encode("utf-8")) > 50_000
        and "leroy merlin" in lowered
        and (
            "/productos/" in lowered
            or "header" in lowered
            or "footer" in lowered
            or "search" in lowered
            or "categor" in lowered
        )
    )
    if has_usable_page and "please enable js" not in lowered:
        return False
    markers = [
        "captcha-delivery.com",
        "please enable js",
        "var dd=",
        "var dd =",
        "enable cookies",
        "access denied",
    ]
    return any(marker in lowered for marker in markers)


def normalize_text(content: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_product_jsonld(content: str) -> dict:
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for script in scripts:
        raw = unescape(script).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if isinstance(entry, dict) and entry.get("@type") == "Product":
                return entry
    return {}


def extract_availability(content: str) -> tuple[str, bool, str]:
    product = extract_product_jsonld(content)
    offers = product.get("offers", {}) if isinstance(product, dict) else {}
    availability = ""
    if isinstance(offers, dict):
        availability = str(offers.get("availability", "") or "")

    text = normalize_text(content)
    unavailable_markers = [
        "este producto no está disponible",
        "este producto no esta disponible",
        "producto no disponible",
        "not available",
        "out of stock",
        "discontinued",
    ]
    positive_markers = [
        "añadir al carrito",
        "anadir al carrito",
        "disponible",
        "en stock",
    ]

    availability_lower = availability.lower()
    if "discontinued" in availability_lower or "outofstock" in availability_lower:
        return availability or "negative_marker", False, f"jsonld availability={availability}"
    if '"add_to_cart_availability":true' in content:
        return availability or "add_to_cart_available", True, "add_to_cart_availability=true"
    if "recommendation-no-offer-banner" in content:
        return availability or "recommendation_no_offer_banner", False, "recommendation-no-offer-banner"
    if '"total_offer_count":0' in content and '"name":"cdl_products"' in content:
        return availability or "zero_offer_count", False, "cdl_products total_offer_count=0"
    if any(marker in text for marker in unavailable_markers):
        return availability or "text_unavailable", False, "texto de no disponibilidad"
    if "instock" in availability_lower or any(marker in text for marker in positive_markers):
        return availability or "text_available", True, "marcador positivo de disponibilidad"
    return availability or "unknown", False, "sin senal comprable"


def redact_cookie(cookie: dict) -> dict:
    value = str(cookie.get("value", ""))
    redacted = dict(cookie)
    redacted["value"] = "<redacted>"
    redacted["value_sha256_12"] = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""
    return redacted


def write_csv(path: Path, rows: list[BrowserCheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(asdict(rows[0]).keys()) if rows else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def append_csv(path: Path, row: BrowserCheckResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        fieldnames = list(asdict(row).keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(asdict(row))


def minimize_chromium_window(context, page) -> None:
    try:
        session = context.new_cdp_session(page)
        window = session.send("Browser.getWindowForTarget")
        window_id = window.get("windowId")
        if window_id is not None:
            session.send(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"windowState": "minimized"}},
            )
    except Exception:
        pass


def decide(
    ean: str,
    content: str,
    candidates: list[str],
    is_challenge: bool,
    product_availability: str,
    offer_available: bool,
    availability_evidence: str,
) -> tuple[str, str]:
    if is_challenge:
        return "INCIERTA", "challenge detectado en navegador"
    if len(content.encode("utf-8")) < 10_000:
        return "INCIERTA", "HTML renderizado demasiado pequeno"
    if ean in content and not offer_available:
        return "NO_VIVA", f"EAN encontrado pero oferta no disponible ({product_availability}; {availability_evidence})"
    if ean in content and offer_available:
        return "VIVA", f"EAN encontrado y oferta disponible ({product_availability}; {availability_evidence})"
    if candidates:
        return "INCIERTA", "hay URLs candidatas, pero no se confirmo EAN ni disponibilidad"
    return "NO_ENCONTRADA_PRELIMINAR", "busqueda renderizada sin EAN ni candidatos"


def run(args: argparse.Namespace) -> int:
    started_at = time.monotonic()
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install playwright", file=sys.stderr)
        return 2

    eans = read_eans(args.ean_file)
    if args.limit:
        eans = eans[: args.limit]
    if not eans:
        print("No EANs found", file=sys.stderr)
        return 2

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run.log"

    def log(message: str) -> None:
        print(message, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")

    results: list[BrowserCheckResult] = []
    with sync_playwright() as p:
        log(f"Using profile: {PROFILE_DIR}")
        log(f"Writing output: {output_dir}")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1365, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Madrid",
            args=["--disable-blink-features=AutomationControlled", "--start-minimized"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        minimize_chromium_window(context, page)
        page.set_default_timeout(args.timeout * 1000)

        if args.bootstrap_home:
            log(f"Opening home first: {HOME_URL}")
            try:
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=args.timeout * 1000)
            except PlaywrightTimeoutError:
                log("Home load timed out; continuing with current page state.")
            if args.wait_solved > 0:
                deadline = time.monotonic() + args.wait_solved
                while True:
                    title_now = page.title()
                    content_now = page.content()
                    challenged_now = challenge_detected(content_now, title_now, page.url)
                    if not challenged_now:
                        log("No challenge detected on home.")
                        break
                    if time.monotonic() >= deadline:
                        log("Challenge still visible on home after wait timeout.")
                        break
                    log("Challenge detected on home. Resolve it in the browser window; checking again in 5 seconds.")
                    time.sleep(5)

        for index, ean in enumerate(eans, start=1):
            url = BASE_SEARCH_URL.format(ean=ean)
            log(f"[{index}/{len(eans)}] opening {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
            except PlaywrightTimeoutError:
                log("Initial load timed out; continuing with current page state.")
            except PlaywrightError as exc:
                log(f"Navigation error: {exc}")
                try:
                    page.close()
                except PlaywrightError:
                    pass
                page = context.new_page()
                minimize_chromium_window(context, page)
                page.set_default_timeout(args.timeout * 1000)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                except PlaywrightTimeoutError:
                    log("Retry load timed out; continuing with current page state.")
                except PlaywrightError as retry_exc:
                    log(f"Retry navigation failed: {retry_exc}")
                    row = BrowserCheckResult(
                        ean=ean,
                        status="INCIERTA",
                        final_url=url,
                        title="",
                        html_path="",
                        screenshot_path="",
                        cookies_path="",
                        html_bytes=0,
                        ean_in_html=False,
                        product_availability="unknown",
                        offer_available=False,
                        availability_evidence="navigation_error",
                        candidate_count=0,
                        first_candidate_url="",
                        challenge_detected=False,
                        reason=f"error de navegacion: {retry_exc}",
                    )
                    results.append(row)
                    append_csv(output_dir / "summary_live.csv", row)
                    if index < len(eans):
                        time.sleep(args.delay)
                    continue

            if args.manual:
                print("")
                print("Resolve any visible challenge in the browser window.")
                print("When the page is usable, return here and press Enter.")
                input()

            if args.wait_solved > 0:
                deadline = time.monotonic() + args.wait_solved
                while True:
                    title_now = page.title()
                    content_now = page.content()
                    challenged_now = challenge_detected(content_now, title_now, page.url)
                    if not challenged_now:
                        break
                    if time.monotonic() >= deadline:
                        log("Challenge still visible after wait timeout; saving current evidence.")
                        break
                    log("Challenge detected. Resolve it in the browser window; checking again in 5 seconds.")
                    time.sleep(5)

            try:
                if args.networkidle_timeout > 0:
                    page.wait_for_load_state("networkidle", timeout=args.networkidle_timeout * 1000)
            except PlaywrightTimeoutError:
                pass

            title = page.title()
            final_url = page.url
            content = page.content()
            candidates = extract_candidate_urls(content)
            is_challenge = challenge_detected(content, title, final_url)
            product_availability, offer_available, availability_evidence = extract_availability(content)
            status, reason = decide(
                ean,
                content,
                candidates,
                is_challenge,
                product_availability,
                offer_available,
                availability_evidence,
            )

            safe_name = f"{index:03d}_{ean}"
            html_path = output_dir / f"{safe_name}.html"
            screenshot_path = output_dir / f"{safe_name}.png"
            cookies_path = output_dir / f"{safe_name}_cookies_redacted.json"
            should_write_html = (
                args.html_mode == "all"
                or (args.html_mode == "failures" and status != "VIVA")
            )
            html_output = str(html_path) if should_write_html else ""
            screenshot_output = str(screenshot_path)
            cookies_output = str(cookies_path)
            if should_write_html:
                html_path.write_text(content, encoding="utf-8")
            if args.skip_screenshot:
                screenshot_output = ""
            else:
                page.screenshot(path=str(screenshot_path), full_page=True)
            if args.skip_cookies:
                cookies_output = ""
            else:
                cookies = [redact_cookie(cookie) for cookie in context.cookies("https://www.leroymerlin.es/")]
                cookies_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

            row = BrowserCheckResult(
                ean=ean,
                status=status,
                final_url=final_url,
                title=title,
                html_path=html_output,
                screenshot_path=screenshot_output,
                cookies_path=cookies_output,
                html_bytes=len(content.encode("utf-8")),
                ean_in_html=ean in content,
                product_availability=product_availability,
                offer_available=offer_available,
                availability_evidence=availability_evidence,
                candidate_count=len(candidates),
                first_candidate_url=candidates[0] if candidates else "",
                challenge_detected=is_challenge,
                reason=reason,
            )
            results.append(row)
            append_csv(output_dir / "summary_live.csv", row)

            if index < len(eans):
                time.sleep(args.delay)

        summary_path = output_dir / "summary.csv"
        write_csv(summary_path, results)
        elapsed_seconds = time.monotonic() - started_at
        status_counts = dict(Counter(row.status for row in results))
        log(f"Summary: {summary_path}")
        log(f"Elapsed seconds: {elapsed_seconds:.1f}")
        log(f"Status counts: {json.dumps(status_counts, ensure_ascii=False, sort_keys=True)}")
        if not args.suppress_final_json:
            log(json.dumps([asdict(row) for row in results], ensure_ascii=False, indent=2))

        if args.keep_open:
            log("Browser kept open. Press Enter here to close it.")
            input()

        context.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ean-file", type=Path, default=Path("Referencias.csv"))
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--delay", type=float, default=10.0)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--networkidle-timeout", type=int, default=15)
    parser.add_argument("--manual", action="store_true", help="Pause after each page load for manual challenge solving.")
    parser.add_argument("--wait-solved", type=int, default=0, help="Seconds to wait while a visible challenge is solved.")
    parser.add_argument("--keep-open", action="store_true", help="Keep browser open before exiting.")
    parser.add_argument("--bootstrap-home", action="store_true", help="Open Leroy home first to establish the dedicated session.")
    parser.add_argument("--skip-screenshot", action="store_true", help="Skip screenshots for faster routine checks.")
    parser.add_argument("--skip-cookies", action="store_true", help="Skip redacted cookie export for faster routine checks.")
    parser.add_argument(
        "--html-mode",
        choices=["all", "failures", "none"],
        default="all",
        help="Control HTML evidence persistence.",
    )
    parser.add_argument("--suppress-final-json", action="store_true", help="Do not print every result at the end.")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
