import csv
import hashlib
import json
import queue
import re
import shutil
import sqlite3
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from html import unescape
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
FASE_DIR = BASE_DIR / "fase1"
PROFILE_DIR = FASE_DIR / "browser_profile_leroy"
RUNS_DIR = FASE_DIR / "dashboard_runs"
CACHE_DB_PATH = FASE_DIR / "offer_cache.sqlite"
LOCAL_SETTINGS_PATH = BASE_DIR / "local_settings.json"
LEROY_HOME_URL = "https://www.leroymerlin.es/"
LEROY_SEARCH_URL = "https://www.leroymerlin.es/search?q={ean}"
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_URL_PARTS = (
    "googletagmanager",
    "google-analytics",
    "doubleclick",
    "facebook.net",
    "hotjar",
    "newrelic",
    "contentsquare",
)


@dataclass
class InputProduct:
    ean: str
    reference: str = ""
    quantity: str = ""
    price: str = ""


@dataclass
class DashboardResult:
    ean: str
    reference: str
    feed_quantity: str
    feed_price: str
    light: str
    status: str
    final_url: str
    title: str
    sku: str
    seller_name: str
    marketplace_price: str
    product_availability: str
    offer_available: bool
    buybox_ok: str
    challenge_detected: bool
    reason: str
    elapsed_seconds: float
    html_path: str


@dataclass
class WorkerConfig:
    id: int
    enabled: bool = True
    proxy_server: str = ""
    proxy_username: str = ""
    proxy_password: str = ""
    user_agent: str = ""

    @property
    def proxy_configured(self) -> bool:
        return bool(self.proxy_server.strip())

    @property
    def user_agent_configured(self) -> bool:
        return bool(self.user_agent.strip())


def read_local_settings() -> dict:
    if not LOCAL_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_worker_configs(worker_count: int) -> list[WorkerConfig]:
    worker_count = max(1, min(int(worker_count), 10))
    settings = read_local_settings()
    configured: dict[int, WorkerConfig] = {}
    raw_workers = settings.get("workers", [])
    if isinstance(raw_workers, list):
        for item in raw_workers:
            if not isinstance(item, dict):
                continue
            try:
                worker_id = int(item.get("id", 0))
            except (TypeError, ValueError):
                continue
            if worker_id < 1 or worker_id > 10:
                continue
            configured[worker_id] = WorkerConfig(
                id=worker_id,
                enabled=bool(item.get("enabled", True)),
                proxy_server=str(item.get("proxy_server", "") or "").strip(),
                proxy_username=str(item.get("proxy_username", "") or "").strip(),
                proxy_password=str(item.get("proxy_password", "") or "").strip(),
                user_agent=str(item.get("user_agent", "") or "").strip(),
            )
    return [configured.get(worker_id, WorkerConfig(id=worker_id)) for worker_id in range(1, worker_count + 1)]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def parse_quantity(value: str) -> float | None:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def product_feed_signature(product: InputProduct) -> str:
    raw = "\n".join(
        [
            product.ean.strip(),
            product.reference.strip(),
            product.quantity.strip(),
            product.price.strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_products_csv(path: Path) -> list[InputProduct]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    first_line = raw.splitlines()[0] if raw.splitlines() else ""
    delimiter = ";"
    if first_line.count(",") > first_line.count(";"):
        delimiter = ","
    if "\t" in first_line and first_line.count("\t") > first_line.count(delimiter):
        delimiter = "\t"

    rows = list(csv.DictReader(raw.splitlines(), delimiter=delimiter))
    products: list[InputProduct] = []
    if rows and rows[0]:
        field_map = {normalize(name): name for name in rows[0].keys()}
        ean_key = field_map.get("ean") or field_map.get("gtin") or field_map.get("barcode")
        ref_key = field_map.get("reference") or field_map.get("sku") or field_map.get("ref")
        qty_key = field_map.get("quantity") or field_map.get("stock") or field_map.get("qty")
        price_key = field_map.get("price") or field_map.get("precio")
        if ean_key:
            for row in rows:
                ean = (row.get(ean_key) or "").strip()
                if ean:
                    products.append(
                        InputProduct(
                            ean=ean,
                            reference=(row.get(ref_key) or "").strip() if ref_key else "",
                            quantity=(row.get(qty_key) or "").strip() if qty_key else "",
                            price=(row.get(price_key) or "").strip() if price_key else "",
                        )
                    )
            return products

    for line in raw.splitlines():
        ean = line.strip().split(";")[0].strip().split(",")[0].strip()
        if ean and ean.lower() != "ean":
            products.append(InputProduct(ean=ean))
    return products


def extract_candidate_urls(content: str) -> list[str]:
    patterns = [
        r"https://www\.leroymerlin\.es/productos/[^\"'<>\\\s]+?\.html",
        r"/productos/[^\"'<>\\\s]+?\.html",
    ]
    candidates: list[str] = []
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


def visible_text(content: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip().lower()


def challenge_detected(content: str, title: str, url: str) -> bool:
    lowered = f"{title}\n{url}\n{content[:200000]}".lower()
    usable = len(content.encode("utf-8")) > 50_000 and "leroy merlin" in lowered
    has_product_signal = (
        'id="jsonld_product"' in lowered
        or '"add_to_cart_availability":true' in content
        or "schema.org/discontinued" in lowered
        or "recommendation-no-offer-banner" in lowered
    )
    if usable and has_product_signal and "please enable js" not in lowered:
        return False
    markers = [
        "captcha-delivery.com",
        "please enable js",
        "var dd=",
        "var dd =",
        "access denied",
        "recaptcha",
        "g-recaptcha",
        "hcaptcha",
        "are you human",
        "unusual traffic",
        "blocked",
        "bot detection",
    ]
    return any(marker in lowered for marker in markers)


def extract_availability(content: str) -> tuple[str, bool, str]:
    product = extract_product_jsonld(content)
    offers = product.get("offers", {}) if isinstance(product, dict) else {}
    availability = ""
    if isinstance(offers, dict):
        availability = str(offers.get("availability", "") or "")

    availability_lower = availability.lower()
    if "discontinued" in availability_lower or "outofstock" in availability_lower:
        return availability or "negative_marker", False, f"jsonld availability={availability}"
    if '"add_to_cart_availability":true' in content:
        return availability or "add_to_cart_available", True, "add_to_cart_availability=true"
    if "recommendation-no-offer-banner" in content:
        return availability or "recommendation_no_offer_banner", False, "recommendation-no-offer-banner"
    if '"total_offer_count":0' in content and '"name":"cdl_products"' in content:
        return availability or "zero_offer_count", False, "cdl_products total_offer_count=0"

    text = visible_text(content)
    for marker in ("este producto no está disponible", "este producto no esta disponible", "producto no disponible"):
        if marker in text:
            return availability or "text_unavailable", False, "texto de no disponibilidad"
    return availability or "unknown", False, "sin senal comprable"


def extract_first(pattern: str, content: str) -> str:
    match = re.search(pattern, content, flags=re.IGNORECASE | re.DOTALL)
    return unescape(match.group(1)).strip() if match else ""


def extract_product_fields(content: str) -> dict[str, str]:
    product = extract_product_jsonld(content)
    offers = product.get("offers", {}) if isinstance(product, dict) else {}
    sku = extract_first(r'"sku"\s*:\s*"([^"]+)"', content)
    seller_name = extract_first(r'"seller_name"\s*:\s*"([^"]+)"', content)
    price = extract_first(r'"unitprice_ati"\s*:\s*([0-9]+(?:\.[0-9]+)?)', content)
    if not price and isinstance(offers, dict):
        price = str(offers.get("price", "") or "")
    return {"sku": sku, "seller_name": seller_name, "marketplace_price": price}


def classify_light(
    product: InputProduct,
    content: str,
    title: str,
    final_url: str,
    expected_seller: str,
) -> tuple[str, str, str, bool, str, str, str, str]:
    candidates = extract_candidate_urls(content)
    is_challenge = challenge_detected(content, title, final_url)
    availability, offer_available, availability_evidence = extract_availability(content)
    fields = extract_product_fields(content)
    seller_name = fields["seller_name"]
    feed_qty = parse_quantity(product.quantity)

    if is_challenge:
        return "gray", "INCIERTA", availability, offer_available, "unknown", seller_name, fields["marketplace_price"], "challenge detectado"
    if feed_qty is not None and feed_qty <= 0:
        return "red", "SIN_STOCK_FEED", availability, offer_available, "n/a", seller_name, fields["marketplace_price"], "stock feed <= 0"
    if len(content.encode("utf-8")) < 10_000:
        return "gray", "INCIERTA", availability, offer_available, "unknown", seller_name, fields["marketplace_price"], "HTML demasiado pequeno"
    if product.ean not in content and not candidates:
        return "red", "NO_VIVA", availability, offer_available, "n/a", seller_name, fields["marketplace_price"], "no se vende en marketplace"
    if product.ean not in content and candidates:
        return "gray", "INCIERTA", availability, offer_available, "unknown", seller_name, fields["marketplace_price"], "candidatos sin EAN confirmado"
    if not offer_available:
        seller_name = ""
        fields["marketplace_price"] = ""
        if feed_qty is not None and feed_qty > 0:
            return "yellow", "NO_DISPONIBLE_CON_STOCK", availability, offer_available, "n/a", seller_name, fields["marketplace_price"], availability_evidence
        return "red", "NO_VIVA", availability, offer_available, "n/a", seller_name, fields["marketplace_price"], availability_evidence

    buybox_ok = "n/a"
    if expected_seller.strip():
        buybox_ok = "yes" if normalize(seller_name) == normalize(expected_seller) else "no"
        if buybox_ok == "no":
            return "yellow", "BUYBOX_PERDIDA", availability, offer_available, buybox_ok, seller_name, fields["marketplace_price"], f"seller actual={seller_name}"

    return "green", "OK", availability, offer_available, buybox_ok, seller_name, fields["marketplace_price"], "oferta disponible"


def write_dashboard_row(path: Path, row: DashboardResult) -> None:
    exists = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(row).keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(asdict(row))


class OfferCache:
    def __init__(self, path: Path = CACHE_DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS offer_results (
                    ean TEXT NOT NULL,
                    expected_seller TEXT NOT NULL,
                    feed_signature TEXT NOT NULL,
                    checked_at REAL NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY (ean, expected_seller)
                )
                """
            )

    def get_fresh(
        self,
        product: InputProduct,
        expected_seller: str,
        ttl_hours: float,
    ) -> DashboardResult | None:
        expected_seller = (expected_seller or "").strip()
        signature = product_feed_signature(product)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT feed_signature, checked_at, result_json
                FROM offer_results
                WHERE ean = ? AND expected_seller = ?
                """,
                (product.ean, expected_seller),
            ).fetchone()
        if not row:
            return None
        if row["feed_signature"] != signature:
            return None
        max_age_seconds = max(ttl_hours, 0) * 3600
        if max_age_seconds and (time.time() - float(row["checked_at"])) > max_age_seconds:
            return None
        data = json.loads(row["result_json"])
        if data.get("status") == "INCIERTA" or data.get("light") == "gray":
            return None
        data.update(
            {
                "reference": product.reference,
                "feed_quantity": product.quantity,
                "feed_price": product.price,
                "reason": f"cache diferencial: {data.get('reason', '')}".strip(),
                "elapsed_seconds": 0.0,
            }
        )
        return DashboardResult(**data)

    def put(self, product: InputProduct, expected_seller: str, row: DashboardResult) -> None:
        if row.status == "INCIERTA" or row.light == "gray":
            return
        data = asdict(row)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO offer_results (ean, expected_seller, feed_signature, checked_at, result_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ean, expected_seller) DO UPDATE SET
                    feed_signature = excluded.feed_signature,
                    checked_at = excluded.checked_at,
                    result_json = excluded.result_json
                """,
                (
                    product.ean,
                    (expected_seller or "").strip(),
                    product_feed_signature(product),
                    time.time(),
                    json.dumps(data, ensure_ascii=False),
                ),
            )


class AlertNotifier:
    def __init__(self):
        self.settings = self._load_settings()
        self.enabled = self._setting_bool("alerts_enabled", True)
        self.slack_webhook_url = (
            self._env("SLACK_WEBHOOK_URL")
            or str(self.settings.get("slack_webhook_url", "") or "").strip()
        )
        self.cooldown_seconds = int(self._setting_float("alert_cooldown_minutes", 15.0) * 60)
        self.sent_at: dict[str, float] = {}

    def _load_settings(self) -> dict:
        return read_local_settings()

    def _env(self, name: str) -> str:
        import os

        return os.environ.get(name, "").strip()

    def _setting_bool(self, name: str, default: bool) -> bool:
        value = self._env(name.upper())
        if not value:
            value = self.settings.get(name, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    def _setting_float(self, name: str, default: float) -> float:
        value = self._env(name.upper())
        if not value:
            value = self.settings.get(name, default)
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return default

    def should_alert(self, row: DashboardResult) -> bool:
        evidence = f"{row.status} {row.reason} {row.title} {row.final_url}".casefold()
        markers = (
            "captcha",
            "recaptcha",
            "hcaptcha",
            "challenge",
            "datadome",
            "access denied",
            "blocked",
            "bloqueo",
            "error de navegacion",
            "timeout",
            "please enable js",
        )
        return row.challenge_detected or row.status == "INCIERTA" or any(marker in evidence for marker in markers)

    def notify_if_needed(self, row: DashboardResult, run_dir: Path, index: int, total: int) -> bool:
        if not self.enabled or not self.slack_webhook_url or not self.should_alert(row):
            return False
        key = row.status if row.status else "technical_alert"
        now = time.time()
        if self.cooldown_seconds > 0 and now - self.sent_at.get(key, 0) < self.cooldown_seconds:
            return False
        self.sent_at[key] = now
        return self.send_slack(row, run_dir, index, total)

    def send_slack(self, row: DashboardResult, run_dir: Path, index: int, total: int) -> bool:
        payload = {
            "text": f"OfferChecker alerta: {row.status} en EAN {row.ean}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*OfferChecker alerta*\nDetectado posible bloqueo/challenge en Leroy Merlin.",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*EAN:*\n`{row.ean}`"},
                        {"type": "mrkdwn", "text": f"*Estado:*\n`{row.status}`"},
                        {"type": "mrkdwn", "text": f"*Progreso:*\n{index}/{total}"},
                        {"type": "mrkdwn", "text": f"*Challenge:*\n{row.challenge_detected}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Motivo:*\n{row.reason[:600]}"},
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Run local: `{run_dir}`"},
                        {"type": "mrkdwn", "text": f"URL: {row.final_url}"},
                    ],
                },
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.slack_webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError):
            return False


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


def install_lightweight_routes(context) -> None:
    def handle_route(route) -> None:
        try:
            request = route.request
            url = request.url.lower()
            if request.resource_type in BLOCKED_RESOURCE_TYPES or any(part in url for part in BLOCKED_URL_PARTS):
                route.abort()
            else:
                route.continue_()
        except Exception:
            pass

    context.route("**/*", handle_route)


class LeroyChecker:
    def __init__(
        self,
        products: list[InputProduct],
        expected_seller: str,
        delay: float,
        nav_timeout: float = 18.0,
        retry_timeout: float = 35.0,
        block_assets: bool = True,
        worker_count: int = 1,
        circuit_breaker_threshold: int = 4,
    ):
        self.products = products
        self.expected_seller = expected_seller
        self.delay = delay
        self.nav_timeout_ms = int(max(nav_timeout, 5.0) * 1000)
        self.retry_timeout_ms = int(max(retry_timeout, nav_timeout, 5.0) * 1000)
        self.block_assets = block_assets
        self.worker_configs = load_worker_configs(worker_count)
        self.active_worker_configs = [config for config in self.worker_configs if config.enabled]
        if not self.active_worker_configs:
            self.active_worker_configs = [WorkerConfig(id=1)]
        self.worker_count = len(self.active_worker_configs)
        self.circuit_breaker_threshold = max(1, int(circuit_breaker_threshold))
        self.stop_requested = False
        self.circuit_open = False
        self.completed_count = 0
        self.challenge_streak = 0
        self.result_lock = threading.Lock()
        self.run_dir = RUNS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.summary_path = self.run_dir / "summary_live.csv"
        self.cache = OfferCache()
        self.alerts = AlertNotifier()

    def stop(self) -> None:
        self.stop_requested = True

    def profile_dir_for_worker(self, worker_id: int) -> Path:
        if worker_id <= 1:
            return PROFILE_DIR
        return FASE_DIR / f"browser_profile_leroy_worker_{worker_id}"

    def launch_worker_context(self, p, worker_id: int, PlaywrightTimeoutError):
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir_for_worker(worker_id)),
            headless=False,
            viewport={"width": 1365, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Madrid",
            args=["--disable-blink-features=AutomationControlled", "--start-minimized"],
        )
        if self.block_assets:
            install_lightweight_routes(context)
        page = context.pages[0] if context.pages else context.new_page()
        minimize_chromium_window(context, page)
        page.set_default_timeout(self.retry_timeout_ms)
        try:
            page.goto(LEROY_HOME_URL, wait_until="domcontentloaded", timeout=self.nav_timeout_ms)
        except PlaywrightTimeoutError:
            pass
        return context, page

    def check_one_product(self, context, page, product: InputProduct, index: int, PlaywrightError) -> tuple[DashboardResult, object]:
        item_started = time.monotonic()
        url = LEROY_SEARCH_URL.format(ean=product.ean)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.nav_timeout_ms)
        except PlaywrightError:
            try:
                page.close()
            except PlaywrightError:
                pass
            page = context.new_page()
            minimize_chromium_window(context, page)
            page.set_default_timeout(self.retry_timeout_ms)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.retry_timeout_ms)
            except PlaywrightError as exc:
                row = DashboardResult(
                    ean=product.ean,
                    reference=product.reference,
                    feed_quantity=product.quantity,
                    feed_price=product.price,
                    light="yellow",
                    status="INCIERTA",
                    final_url=url,
                    title="",
                    sku="",
                    seller_name="",
                    marketplace_price="",
                    product_availability="unknown",
                    offer_available=False,
                    buybox_ok="unknown",
                    challenge_detected=False,
                    reason=f"error de navegacion: {exc}",
                    elapsed_seconds=round(time.monotonic() - item_started, 2),
                    html_path="",
                )
                return row, page

        content = page.content()
        title = page.title()
        final_url = page.url
        light, status, availability, offer_available, buybox_ok, seller_name, marketplace_price, reason = classify_light(
            product, content, title, final_url, self.expected_seller
        )
        html_path = ""
        if light != "green":
            html_file = self.run_dir / f"{index:04d}_{product.ean}.html"
            html_file.write_text(content, encoding="utf-8")
            html_path = str(html_file)

        row = DashboardResult(
            ean=product.ean,
            reference=product.reference,
            feed_quantity=product.quantity,
            feed_price=product.price,
            light=light,
            status=status,
            final_url=final_url,
            title=title,
            sku=extract_product_fields(content)["sku"],
            seller_name=seller_name,
            marketplace_price=marketplace_price,
            product_availability=availability,
            offer_available=offer_available,
            buybox_ok=buybox_ok,
            challenge_detected=challenge_detected(content, title, final_url),
            reason=reason,
            elapsed_seconds=round(time.monotonic() - item_started, 2),
            html_path=html_path,
        )
        return row, page

    def record_result(self, row: DashboardResult, index: int, total: int, events: queue.Queue) -> int:
        with self.result_lock:
            write_dashboard_row(self.summary_path, row)
            self.cache.put(InputProduct(row.ean, row.reference, row.feed_quantity, row.feed_price), self.expected_seller, row)
            if self.alerts.notify_if_needed(row, self.run_dir, index, total):
                events.put(("alert_sent", row.ean, row.status))
            if self.alerts.should_alert(row):
                self.challenge_streak += 1
            else:
                self.challenge_streak = 0
            if self.challenge_streak >= self.circuit_breaker_threshold and not self.circuit_open:
                self.circuit_open = True
                self.stop_requested = True
                events.put(("circuit_breaker", row.ean, row.status, self.challenge_streak))
            self.completed_count += 1
            return self.completed_count

    def browser_worker(
        self,
        worker_id: int,
        work_queue: queue.Queue,
        events: queue.Queue,
        PlaywrightError,
        PlaywrightTimeoutError,
        sync_playwright,
    ) -> None:
        context = None
        try:
            with sync_playwright() as p:
                context, page = self.launch_worker_context(p, worker_id, PlaywrightTimeoutError)
                events.put(("worker_status", worker_id, "activo"))
                total = len(self.products)
                while not self.stop_requested:
                    try:
                        index, product = work_queue.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        if self.stop_requested:
                            break
                        row, page = self.check_one_product(context, page, product, index, PlaywrightError)
                        completed = self.record_result(row, index, total, events)
                        events.put(("result", completed, total, row))
                        if not self.stop_requested and completed < total:
                            time.sleep(self.delay)
                    finally:
                        work_queue.task_done()
        except Exception as exc:
            self.stop_requested = True
            events.put(("error", f"worker {worker_id}: {exc}"))
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            events.put(("worker_status", worker_id, "cerrado"))

    def run(self, events: queue.Queue) -> None:
        started = time.monotonic()
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            events.put(("error", f"Playwright no esta instalado: {exc}"))
            return

        self.run_dir.mkdir(parents=True, exist_ok=True)
        events.put(("run_dir", str(self.run_dir)))
        events.put(("phase3", self.worker_count, self.circuit_breaker_threshold))
        for config in self.worker_configs:
            events.put(
                (
                    "worker_config",
                    config.id,
                    config.enabled,
                    config.proxy_configured,
                    config.user_agent_configured,
                )
            )
            if not config.enabled:
                events.put(("worker_status", config.id, "desactivado"))

        work_queue: queue.Queue = queue.Queue()
        for index, product in enumerate(self.products, start=1):
            work_queue.put((index, product))

        worker_threads = []
        for config in self.active_worker_configs:
            thread = threading.Thread(
                target=self.browser_worker,
                args=(config.id, work_queue, events, PlaywrightError, PlaywrightTimeoutError, sync_playwright),
                daemon=True,
            )
            worker_threads.append(thread)
            thread.start()

        for thread in worker_threads:
            thread.join()

        elapsed = round(time.monotonic() - started, 1)
        summary = str(self.summary_path)
        if self.circuit_open:
            summary = f"{summary} - corte tecnico activo"
        events.put(("done", elapsed, summary))


class MarketplaceDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.title("Marketplace")
        self.resizable(False, False)
        self.result = "Leroy Merlin"
        self.configure(bg="#f6f7f4")
        self.transient(master)
        self.grab_set()

        frame = ttk.Frame(self, padding=22)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text="Marketplace a checkear", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(frame, state="readonly", values=["Leroy Merlin"], width=30)
        self.combo.set("Leroy Merlin")
        self.combo.grid(row=1, column=0, pady=(12, 18), sticky="ew")
        ttk.Button(frame, text="Continuar", command=self.accept).grid(row=2, column=0, sticky="e")
        self.bind("<Return>", lambda _event: self.accept())
        self.wait_visibility()
        self.focus_force()

    def accept(self) -> None:
        self.result = self.combo.get()
        self.destroy()


class DashboardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Offer Watcher")
        self.geometry("1240x760")
        self.minsize(1100, 680)
        self.configure(bg="#f5f6f2")
        self.events: queue.Queue = queue.Queue()
        self.products: list[InputProduct] = []
        self.checker: LeroyChecker | None = None
        self.worker: threading.Thread | None = None
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#f5f6f2")
        self.style.configure("TLabel", background="#f5f6f2", foreground="#1f2a24", font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        self.style.configure("TButton", font=("Segoe UI", 10), padding=8)
        self.style.configure("Treeview", rowheight=30, font=("Segoe UI", 9), fieldbackground="#ffffff")
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        dialog = MarketplaceDialog(self)
        self.marketplace = dialog.result
        self.build_ui()
        self.after(200, self.process_events)

    def build_ui(self) -> None:
        top = ttk.Frame(self, padding=(20, 16, 20, 8))
        top.pack(fill="x")

        logo = tk.Canvas(top, width=210, height=58, bg="#f5f6f2", highlightthickness=0)
        logo.grid(row=0, column=0, rowspan=2, sticky="w")
        logo.create_rectangle(0, 6, 190, 54, fill="#007a3d", outline="#007a3d")
        logo.create_polygon(18, 43, 48, 15, 78, 43, fill="white", outline="white")
        logo.create_text(126, 30, text="LEROY\nMERLIN", fill="white", font=("Segoe UI", 12, "bold"), justify="center")

        ttk.Label(top, text="Disponibilidad Marketplace", style="Header.TLabel").grid(row=0, column=1, sticky="w")
        self.marketplace_var = tk.StringVar(value=self.marketplace)
        ttk.Combobox(top, textvariable=self.marketplace_var, values=["Leroy Merlin"], state="readonly", width=24).grid(
            row=1, column=1, sticky="w", pady=(6, 0)
        )

        status_frame = ttk.Frame(top)
        status_frame.grid(row=0, column=2, rowspan=2, sticky="e")
        top.columnconfigure(2, weight=1)
        self.green_label = ttk.Label(status_frame, text="● 0 OK", foreground="#11823b", font=("Segoe UI", 11, "bold"))
        self.yellow_label = ttk.Label(status_frame, text="● 0 Revisar", foreground="#b77900", font=("Segoe UI", 11, "bold"))
        self.red_label = ttk.Label(status_frame, text="● 0 Fuera", foreground="#bd1e24", font=("Segoe UI", 11, "bold"))
        self.gray_label = ttk.Label(status_frame, text="● 0 Tecnico", foreground="#6b7280", font=("Segoe UI", 11, "bold"))
        self.green_label.grid(row=0, column=0, padx=12)
        self.yellow_label.grid(row=0, column=1, padx=12)
        self.red_label.grid(row=0, column=2, padx=12)
        self.gray_label.grid(row=0, column=3, padx=12)

        controls = ttk.Frame(self, padding=(20, 8, 20, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="EAN").grid(row=0, column=0, sticky="w")
        self.ean_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.ean_var, width=32).grid(row=1, column=0, sticky="ew", padx=(0, 12))
        ttk.Button(controls, text="Agregar EAN", command=self.add_single_ean).grid(row=1, column=1, padx=(0, 8))
        ttk.Button(controls, text="Cargar CSV bulk", command=self.load_bulk).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(controls, text="Limpiar lista", command=self.clear_list).grid(row=1, column=3, padx=(0, 8))
        ttk.Button(controls, text="Limpiar perfil", command=self.clean_profile).grid(row=1, column=4, padx=(0, 8))
        controls.columnconfigure(0, weight=1)

        options = ttk.Frame(self, padding=(20, 0, 20, 8))
        options.pack(fill="x")
        self.expected_seller_var = tk.StringVar(value="NEWLUX GROUP")
        self.delay_var = tk.StringVar(value="2")
        ttk.Label(options, text="Seller esperado").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.expected_seller_var, width=28).grid(row=0, column=1, sticky="w", padx=(8, 18))
        ttk.Label(options, text="Delay").grid(row=0, column=2, sticky="w")
        ttk.Entry(options, textvariable=self.delay_var, width=8).grid(row=0, column=3, sticky="w", padx=(8, 18))
        ttk.Button(options, text="Analizar", command=self.start_analysis).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(options, text="Parar", command=self.stop_analysis).grid(row=0, column=5, padx=(0, 8))
        self.progress_var = tk.StringVar(value="Sin ejecucion")
        ttk.Label(options, textvariable=self.progress_var).grid(row=0, column=6, sticky="w", padx=(18, 0))

        table_frame = ttk.Frame(self, padding=(20, 8, 20, 20))
        table_frame.pack(fill="both", expand=True)
        columns = (
            "light",
            "ean",
            "reference",
            "stock",
            "feed_price",
            "status",
            "seller",
            "market_price",
            "availability",
            "reason",
            "url",
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "light": "",
            "ean": "EAN",
            "reference": "SKU/ref",
            "stock": "Stock",
            "feed_price": "Precio feed",
            "status": "Estado",
            "seller": "Seller",
            "market_price": "Precio LM",
            "availability": "Disponibilidad",
            "reason": "Motivo",
            "url": "URL",
        }
        widths = {
            "light": 46,
            "ean": 122,
            "reference": 110,
            "stock": 70,
            "feed_price": 86,
            "status": 150,
            "seller": 150,
            "market_price": 86,
            "availability": 180,
            "reason": 260,
            "url": 380,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], minwidth=40, anchor="w")
        self.tree.tag_configure("green", background="#eaf6ee", foreground="#0d5f2b")
        self.tree.tag_configure("yellow", background="#fff7df", foreground="#6e5200")
        self.tree.tag_configure("red", background="#fdecec", foreground="#8f171d")
        self.tree.tag_configure("gray", background="#f1f3f5", foreground="#4b5563")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

    def add_single_ean(self) -> None:
        ean = self.ean_var.get().strip()
        if not ean:
            return
        self.products.append(InputProduct(ean=ean))
        self.tree.insert("", "end", values=("○", ean, "", "", "", "PENDIENTE", "", "", "", "", ""), tags=("pending",))
        self.ean_var.set("")
        self.progress_var.set(f"{len(self.products)} productos cargados")

    def load_bulk(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecciona CSV",
            filetypes=[("CSV", "*.csv"), ("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            self.products = read_products_csv(Path(path))
        except Exception as exc:
            messagebox.showerror("Error CSV", str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        for product in self.products:
            self.tree.insert(
                "",
                "end",
                values=("○", product.ean, product.reference, product.quantity, product.price, "PENDIENTE", "", "", "", "", ""),
            )
        self.progress_var.set(f"{len(self.products)} productos cargados")

    def clear_list(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de limpiar la lista.")
            return
        self.products = []
        self.tree.delete(*self.tree.get_children())
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        self.update_counts()
        self.progress_var.set("Lista limpia")

    def clean_profile(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de limpiar el perfil.")
            return
        if PROFILE_DIR.exists():
            shutil.rmtree(PROFILE_DIR)
        self.progress_var.set("Perfil dedicado limpiado")

    def start_analysis(self) -> None:
        if not self.products:
            self.add_single_ean()
        if not self.products:
            messagebox.showwarning("Sin productos", "Agrega un EAN o carga un CSV.")
            return
        if self.worker and self.worker.is_alive():
            return
        try:
            delay = float(self.delay_var.get().replace(",", "."))
        except ValueError:
            delay = 2.0
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        self.update_counts()
        self.tree.delete(*self.tree.get_children())
        for product in self.products:
            self.tree.insert("", "end", values=("○", product.ean, product.reference, product.quantity, product.price, "PENDIENTE", "", "", "", "", ""))
        self.checker = LeroyChecker(self.products, self.expected_seller_var.get(), delay)
        self.worker = threading.Thread(target=self.checker.run, args=(self.events,), daemon=True)
        self.worker.start()
        self.progress_var.set("Analizando...")

    def stop_analysis(self) -> None:
        if self.checker:
            self.checker.stop()
            self.progress_var.set("Parando al finalizar el producto actual...")

    def update_counts(self) -> None:
        self.green_label.configure(text=f"● {self.counts['green']} OK")
        self.yellow_label.configure(text=f"● {self.counts['yellow']} Revisar")
        self.red_label.configure(text=f"● {self.counts['red']} Fuera")
        self.gray_label.configure(text=f"● {self.counts['gray']} Tecnico")

    def process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "result":
                    _, index, total, row = event
                    children = self.tree.get_children()
                    item = children[index - 1] if index - 1 < len(children) else self.tree.insert("", "end")
                    symbol = {"green": "●", "yellow": "●", "red": "●"}.get(row.light, "●")
                    self.tree.item(
                        item,
                        values=(
                            symbol,
                            row.ean,
                            row.reference,
                            row.feed_quantity,
                            row.feed_price,
                            row.status,
                            row.seller_name,
                            row.marketplace_price,
                            row.product_availability,
                            row.reason,
                            row.final_url,
                        ),
                        tags=(row.light,),
                    )
                    if row.light in self.counts:
                        self.counts[row.light] += 1
                        self.update_counts()
                    self.progress_var.set(f"{index}/{total} analizados")
                elif kind == "done":
                    _, elapsed, summary = event
                    self.progress_var.set(f"Terminado en {elapsed}s · {summary}")
                elif kind == "run_dir":
                    self.progress_var.set(f"Salida: {event[1]}")
                elif kind == "error":
                    messagebox.showerror("Error", event[1])
        except queue.Empty:
            pass
        self.after(200, self.process_events)


def main() -> None:
    app = DashboardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
