import argparse
import queue
import sys
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard_leroy import (  # noqa: E402
    CarrefourChecker,
    InputProduct,
    build_marketplace_search_url,
    challenge_detected,
    chunk_products,
    get_offer_cache_path,
    minimize_chromium_window,
    read_products_csv,
    show_chromium_window,
    visible_text,
)


FEED_PATH = ROOT_DIR / "fase1" / "shoppingfeed_carrefour_latest.csv"


class VisibleCarrefourChecker(CarrefourChecker):
    window_state = "maximized"

    def sync_window_state(self, context, page) -> None:
        if self.window_state == "minimized":
            minimize_chromium_window(context, page)
        else:
            show_chromium_window(context, page)

    def launch_worker_context(self, p, worker_id: int, PlaywrightTimeoutError):
        print(f"[step 1] Launching Carrefour worker {worker_id} window_state={self.window_state}")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir_for_worker(worker_id)),
            headless=False,
            viewport={"width": 1600, "height": 950},
            locale="es-ES",
            timezone_id="Europe/Madrid",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-quic",
                "--start-minimized" if self.window_state == "minimized" else "--start-maximized",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(self.retry_timeout_ms)
        self.sync_window_state(context, page)

        print(f"[step 2] Warm-up: {self.marketplace_config.home_url}")
        warmup_error = ""
        try:
            page.goto(self.marketplace_config.home_url, wait_until="domcontentloaded", timeout=self.nav_timeout_ms)
        except PlaywrightTimeoutError as exc:
            warmup_error = f"timeout warm-up: {exc}"
            print(f"[warn] {warmup_error}")

        self.sync_window_state(context, page)
        print("[step 3] Waiting for load/network/data settle")
        self.settle_and_stop(page)
        self.sync_window_state(context, page)

        try:
            content = page.content()
            title = page.title()
            final_url = page.url
        except Exception as exc:
            return context, page, False, f"error warm-up: {exc}"

        print(f"[step 4] Warm-up title: {title}")
        print(f"[step 4] Warm-up url: {final_url}")
        print(f"[step 4] Warm-up html bytes: {len(content.encode('utf-8'))}")
        if challenge_detected(content, title, final_url):
            html_file = self.run_dir / f"worker_{worker_id:02d}_warmup_challenge.html"
            html_file.write_text(content, encoding="utf-8")
            print(f"[block] Challenge detected in warm-up. HTML saved: {html_file}")
            return context, page, False, "challenge en warm-up Carrefour"

        print("[ok] Warm-up healthy")
        return context, page, True, warmup_error or "warm-up correcto"

    def check_visible_batch(self, context, page, batch: list[InputProduct], batch_index: int, PlaywrightError):
        url = build_marketplace_search_url(self.marketplace_key, [product.ean for product in batch])
        print(f"[step 5] Batch {batch_index}: {len(batch)} EAN(s)")
        for product in batch:
            print(f"         - {product.ean} | ref={product.reference} | stock={product.quantity} | price={product.price}")
        print(f"[step 6] Opening search URL: {url}")

        started = time.monotonic()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.nav_timeout_ms)
        except PlaywrightError as exc:
            print(f"[warn] First navigation failed: {exc}")
            try:
                page.close()
            except PlaywrightError:
                pass
            page = context.new_page()
            page.set_default_timeout(self.retry_timeout_ms)
            self.sync_window_state(context, page)
            print("[step 6b] Retrying search in a fresh visible page")
            page.goto(url, wait_until="domcontentloaded", timeout=self.retry_timeout_ms)

        self.sync_window_state(context, page)
        print("[step 7] Waiting for Carrefour search results to finish rendering")
        self.settle_and_stop(page)
        self.sync_window_state(context, page)

        content = page.content()
        title = page.title()
        final_url = page.url
        elapsed = round(time.monotonic() - started, 2)
        html_file = self.run_dir / f"carrefour_visible_batch_{batch_index:04d}.html"
        html_file.write_text(content, encoding="utf-8")

        cards = self.extract_search_cards(content)
        text = visible_text(content)
        print(f"[step 8] Final title: {title}")
        print(f"[step 8] Final url: {final_url}")
        print(f"[step 8] HTML bytes: {len(content.encode('utf-8'))}")
        print(f"[step 8] Extracted cards: {len(cards)}")
        print(f"[step 8] Has no-results text: {'sin resultados' in text or 'no se han encontrado resultados' in text}")
        print(f"[step 8] HTML saved: {html_file}")

        rows = self.classify_batch(batch, content, title, final_url, elapsed, str(html_file))
        rows, page = self.retry_unmapped_batch_rows(context, page, rows, batch, batch_index, PlaywrightError)
        print("[step 9] Classification")
        for row in rows:
            print(f"         {row.ean}: {row.light}/{row.status} | seller={row.seller_name or '-'} | price={row.marketplace_price or '-'} | {row.reason}")
        return rows, page


def load_products(limit: int, eans: list[str]) -> list[InputProduct]:
    if eans:
        return [InputProduct(ean=ean.strip()) for ean in eans if ean.strip()]
    products = read_products_csv(FEED_PATH)
    products = [product for product in products if product.ean and product.quantity.strip() not in {"0", "0.0", "0,0"}]
    return products[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Visible step-by-step Carrefour worker simulation")
    parser.add_argument("--limit", type=int, default=7, help="Number of feed products to include")
    parser.add_argument("--max-batches", type=int, default=1, help="Maximum number of Carrefour search batches to run")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent Carrefour workers to simulate")
    parser.add_argument(
        "--window-state",
        choices=("maximized", "minimized"),
        default="maximized",
        help="Browser window state during the simulation",
    )
    parser.add_argument("--ean", action="append", default=[], help="EAN to test. Repeat for several EANs.")
    parser.add_argument("--hold-seconds", type=int, default=180, help="Seconds to keep the browser open at the end")
    args = parser.parse_args()

    products = load_products(max(1, args.limit), args.ean)
    if not products:
        print(f"[error] No products found. Expected feed at {FEED_PATH}")
        return 1

    worker_count = max(1, min(args.workers, 2))
    checker = VisibleCarrefourChecker(
        products=products,
        expected_seller="NEWLUX GROUP",
        delay=0,
        nav_timeout=30,
        retry_timeout=60,
        block_assets=False,
        minimal_data_mode=False,
        data_settle_ms=3000,
        worker_count=worker_count,
        circuit_breaker_threshold=4,
        cache_path=get_offer_cache_path("carrefour"),
    )
    checker.window_state = args.window_state
    checker.run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[setup] Run dir: {checker.run_dir}")
    print(f"[setup] Profile dir: {checker.profile_dir_for_worker(1)}")

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    batches = chunk_products(products, checker.marketplace_config.search_batch_size)
    if args.max_batches > 0:
        batches = batches[: args.max_batches]

    work_queue: queue.Queue = queue.Queue()
    for batch_index, batch in enumerate(batches, start=1):
        work_queue.put((batch_index, batch))

    completed_lock = threading.Lock()
    completed = 0
    failures: list[str] = []

    def run_worker(worker_id: int) -> None:
        nonlocal completed
        context = None
        try:
            with sync_playwright() as p:
                context, page, healthy, reason = checker.launch_worker_context(p, worker_id, PlaywrightTimeoutError)
                if not healthy:
                    failures.append(f"worker {worker_id} blocked: {reason}")
                    return
                while True:
                    try:
                        batch_index, batch = work_queue.get_nowait()
                    except queue.Empty:
                        break
                    rows, page = checker.check_visible_batch(context, page, batch, batch_index, PlaywrightError)
                    for row in rows:
                        with completed_lock:
                            completed += 1
                            current = completed
                        checker.record_result(row, current, len(products), queue.Queue())
                    if not work_queue.empty():
                        print(f"[next] Worker {worker_id} extraction complete; launching next Carrefour search immediately")
        except Exception as exc:
            failures.append(f"worker {worker_id}: {exc}")
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass

    threads = [
        threading.Thread(target=run_worker, args=(worker_id,), daemon=True)
        for worker_id in range(1, worker_count + 1)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print(f"[done] Summary CSV: {checker.summary_path}")
    if failures:
        for failure in failures:
            print(f"[failure] {failure}")
    print(f"[hold] Browser stays open for {args.hold_seconds}s for manual inspection")
    time.sleep(max(0, args.hold_seconds))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
