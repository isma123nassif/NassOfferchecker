import csv
import json
import queue
import re
import shutil
import threading
import time
import tkinter as tk
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
LEROY_HOME_URL = "https://www.leroymerlin.es/"
LEROY_SEARCH_URL = "https://www.leroymerlin.es/search?q={ean}"


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
    markers = ["captcha-delivery.com", "please enable js", "var dd=", "var dd =", "access denied"]
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


class LeroyChecker:
    def __init__(self, products: list[InputProduct], expected_seller: str, delay: float):
        self.products = products
        self.expected_seller = expected_seller
        self.delay = delay
        self.stop_requested = False
        self.run_dir = RUNS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.summary_path = self.run_dir / "summary_live.csv"

    def stop(self) -> None:
        self.stop_requested = True

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

        with sync_playwright() as p:
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
            page.set_default_timeout(45_000)
            try:
                page.goto(LEROY_HOME_URL, wait_until="domcontentloaded", timeout=45_000)
            except PlaywrightTimeoutError:
                pass

            for index, product in enumerate(self.products, start=1):
                if self.stop_requested:
                    break
                item_started = time.monotonic()
                url = LEROY_SEARCH_URL.format(ean=product.ean)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                except PlaywrightError:
                    try:
                        page.close()
                    except PlaywrightError:
                        pass
                    page = context.new_page()
                    minimize_chromium_window(context, page)
                    page.set_default_timeout(45_000)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
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
                        write_dashboard_row(self.summary_path, row)
                        events.put(("result", index, len(self.products), row))
                        time.sleep(self.delay)
                        continue

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
                write_dashboard_row(self.summary_path, row)
                events.put(("result", index, len(self.products), row))
                if index < len(self.products):
                    time.sleep(self.delay)

            context.close()

        elapsed = round(time.monotonic() - started, 1)
        events.put(("done", elapsed, str(self.summary_path)))


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
