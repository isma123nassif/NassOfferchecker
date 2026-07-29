import json
import os
import queue
import shutil
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from dashboard_leroy import (
    DashboardResult,
    InputProduct,
    LeroyChecker,
    OfferCache,
    PROFILE_DIR,
    parse_quantity,
    read_products_csv,
)


BASE_DIR = Path(__file__).resolve().parent
LOCAL_SETTINGS_PATH = BASE_DIR / "local_settings.json"
SHOPPINGFEED_CACHE_PATH = BASE_DIR / "fase1" / "shoppingfeed_latest.csv"

APP_BG = "#F7F8FA"
PANEL = "#FFFFFF"
BORDER = "#E5E7EB"
TEXT = "#17211B"
MUTED = "#667085"
LEROY = "#007A3D"
GREEN = "#16A34A"
YELLOW = "#F59E0B"
RED = "#DC2626"
GRAY = "#6B7280"

LIGHT_META = {
    "green": ("OK", "Correcto", GREEN),
    "yellow": ("REV", "Revisar", YELLOW),
    "red": ("OUT", "Fuera", RED),
    "gray": ("TECH", "Tecnico", GRAY),
}


class MarketplaceDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Marketplace")
        self.geometry("420x230")
        self.resizable(False, False)
        self.result = "Leroy Merlin"
        self.configure(fg_color=APP_BG)
        self.transient(master)
        self.grab_set()

        box = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=18, border_color=BORDER, border_width=1)
        box.pack(fill="both", expand=True, padx=24, pady=24)
        ctk.CTkLabel(box, text="Elige marketplace", font=("Segoe UI", 22, "bold"), text_color=TEXT).pack(
            anchor="w", padx=22, pady=(22, 4)
        )
        ctk.CTkLabel(box, text="Selecciona donde quieres revisar disponibilidad.", text_color=MUTED).pack(
            anchor="w", padx=22
        )
        self.combo = ctk.CTkComboBox(box, values=["Leroy Merlin"], state="readonly", height=38)
        self.combo.set("Leroy Merlin")
        self.combo.pack(fill="x", padx=22, pady=(20, 18))
        ctk.CTkButton(box, text="Continuar", fg_color=LEROY, hover_color="#006332", command=self.accept).pack(
            anchor="e", padx=22
        )
        self.bind("<Return>", lambda _event: self.accept())
        self.after(100, self.focus_force)

    def accept(self):
        self.result = self.combo.get()
        self.destroy()


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, label: str, color: str, command=None):
        super().__init__(master, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        self.color = color
        self.command = command
        self.indicator = ctk.CTkFrame(self, width=5, fg_color=color, corner_radius=5)
        self.indicator.pack(side="left", fill="y", padx=(0, 12))
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=12)
        self.value = ctk.CTkLabel(content, text="0", font=("Segoe UI", 24, "bold"), text_color=TEXT)
        self.value.pack(anchor="w")
        self.label = ctk.CTkLabel(content, text=label, font=("Segoe UI", 12), text_color=MUTED)
        self.label.pack(anchor="w")
        self.filter_hint = ctk.CTkLabel(content, text="Click para filtrar", font=("Segoe UI", 10), text_color="#98A2B3")
        self.filter_hint.pack(anchor="w", pady=(10, 0))
        for widget in (self, self.indicator, content, self.value, self.label, self.filter_hint):
            widget.bind("<Button-1>", self._clicked)

    def set_value(self, value: int):
        self.value.configure(text=str(value))

    def set_active(self, active: bool):
        self.configure(border_color=self.color if active else BORDER, border_width=2 if active else 1)
        self.filter_hint.configure(text="Filtro activo" if active else "Click para filtrar")

    def _clicked(self, _event=None):
        if self.command:
            self.command()


class ModernDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")
        self.title("Leroy Offer Watcher")
        self.geometry("1360x820")
        self.minsize(1180, 720)
        self.configure(fg_color=APP_BG)

        self.events: queue.Queue = queue.Queue()
        self.products: list[InputProduct] = []
        self.checker: LeroyChecker | None = None
        self.worker: threading.Thread | None = None
        self.catalog_worker: threading.Thread | None = None
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        self.row_urls: dict[str, str] = {}
        self.row_items: dict[str, str] = {}
        self.row_lights: dict[str, str] = {}
        self.row_order: list[str] = []
        self.active_filter: str | None = None
        self.cached_count = 0
        self.direct_count = 0
        self.live_total = 0
        self.shoppingfeed_url = self.load_shoppingfeed_url()

        dialog = MarketplaceDialog(self)
        self.wait_window(dialog)
        self.marketplace = dialog.result

        self.build_ui()
        self.after(200, self.process_events)

    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=248, fg_color="#0B3D24", corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        logo = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=22, pady=(28, 22))
        badge = ctk.CTkFrame(logo, fg_color=LEROY, corner_radius=12, height=72)
        badge.pack(fill="x")
        ctk.CTkLabel(badge, text="LEROY\nMERLIN", text_color="white", font=("Segoe UI", 20, "bold")).pack(
            expand=True
        )

        ctk.CTkLabel(sidebar, text="Marketplace", text_color="#B7D7C3", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=24, pady=(8, 6)
        )
        self.marketplace_box = ctk.CTkComboBox(sidebar, values=["Leroy Merlin"], state="readonly", height=38)
        self.marketplace_box.set(self.marketplace)
        self.marketplace_box.pack(fill="x", padx=22)

        ctk.CTkLabel(sidebar, text="Catalogo vivo", text_color="#B7D7C3", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=24, pady=(28, 6)
        )
        ctk.CTkButton(
            sidebar,
            text="Cargar catalogo Shoppingfeed",
            fg_color=LEROY,
            hover_color="#006332",
            command=self.load_live_catalog,
        ).pack(fill="x", padx=22, pady=(0, 8))
        ctk.CTkLabel(
            sidebar,
            text="Formato: ean;reference;quantity;price",
            text_color="#B7D7C3",
            font=("Segoe UI", 11),
            wraplength=196,
            justify="left",
        ).pack(anchor="w", padx=24, pady=(0, 4))

        ctk.CTkLabel(sidebar, text="Entrada", text_color="#B7D7C3", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=24, pady=(22, 6)
        )
        self.ean_var = ctk.StringVar()
        ctk.CTkEntry(sidebar, textvariable=self.ean_var, placeholder_text="EAN manual", height=40).pack(
            fill="x", padx=22, pady=(0, 10)
        )
        ctk.CTkButton(sidebar, text="Agregar EAN", fg_color="#155E3A", hover_color="#114D30", command=self.add_single_ean).pack(
            fill="x", padx=22, pady=(0, 10)
        )
        ctk.CTkButton(sidebar, text="Cargar CSV manual", fg_color="#155E3A", hover_color="#114D30", command=self.load_bulk).pack(
            fill="x", padx=22, pady=(0, 10)
        )

        ctk.CTkLabel(sidebar, text="Configuracion", text_color="#B7D7C3", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=24, pady=(28, 6)
        )
        self.expected_seller_var = ctk.StringVar(value="NEWLUX GROUP")
        ctk.CTkEntry(sidebar, textvariable=self.expected_seller_var, placeholder_text="Seller esperado", height=38).pack(
            fill="x", padx=22, pady=(0, 10)
        )
        self.delay_var = ctk.StringVar(value="2")
        ctk.CTkEntry(sidebar, textvariable=self.delay_var, placeholder_text="Delay segundos", height=38).pack(
            fill="x", padx=22, pady=(0, 10)
        )
        self.use_cache_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            sidebar,
            text="Cache diferencial",
            variable=self.use_cache_var,
            text_color="#D9F0E0",
            fg_color=LEROY,
            hover_color="#114D30",
        ).pack(anchor="w", padx=22, pady=(2, 10))
        self.cache_ttl_var = ctk.StringVar(value="24")
        ctk.CTkEntry(sidebar, textvariable=self.cache_ttl_var, placeholder_text="TTL cache horas", height=38).pack(
            fill="x", padx=22, pady=(0, 10)
        )
        self.nav_timeout_var = ctk.StringVar(value="18")
        ctk.CTkEntry(sidebar, textvariable=self.nav_timeout_var, placeholder_text="Timeout navegador", height=38).pack(
            fill="x", padx=22, pady=(0, 10)
        )
        self.block_assets_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            sidebar,
            text="Bloquear assets pesados",
            variable=self.block_assets_var,
            text_color="#D9F0E0",
            fg_color=LEROY,
            hover_color="#114D30",
        ).pack(anchor="w", padx=22)

        actions = ctk.CTkFrame(sidebar, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=22, pady=24)
        ctk.CTkButton(actions, text="Limpiar perfil", fg_color="#305744", hover_color="#244636", command=self.clean_profile).pack(
            fill="x", pady=(0, 10)
        )
        ctk.CTkButton(actions, text="Limpiar lista", fg_color="#305744", hover_color="#244636", command=self.clear_list).pack(
            fill="x"
        )

        main = ctk.CTkFrame(self, fg_color=APP_BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Disponibilidad de productos", font=("Segoe UI", 28, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w"
        )
        self.subtitle_var = ctk.StringVar(
            value="Carga el catalogo vivo de Shoppingfeed, pega un EAN o importa un CSV manual."
        )
        ctk.CTkLabel(header, textvariable=self.subtitle_var, text_color=MUTED, font=("Segoe UI", 13)).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ctk.CTkButton(header, text="Analizar", width=132, height=42, fg_color=LEROY, hover_color="#006332", command=self.start_analysis).grid(
            row=0, column=1, rowspan=2, padx=(12, 8)
        )
        ctk.CTkButton(header, text="Parar", width=104, height=42, fg_color="#FFFFFF", text_color=RED, hover_color="#FEE2E2", border_width=1, border_color="#FCA5A5", command=self.stop_analysis).grid(
            row=0, column=2, rowspan=2
        )

        metrics = ctk.CTkFrame(main, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 12))
        for i in range(4):
            metrics.grid_columnconfigure(i, weight=1)
        self.cards = {
            "green": MetricCard(metrics, "Correctos", GREEN, command=lambda: self.set_filter("green")),
            "yellow": MetricCard(metrics, "Revisar", YELLOW, command=lambda: self.set_filter("yellow")),
            "red": MetricCard(metrics, "Fuera", RED, command=lambda: self.set_filter("red")),
            "gray": MetricCard(metrics, "Tecnico", GRAY, command=lambda: self.set_filter("gray")),
        }
        for i, key in enumerate(("green", "yellow", "red", "gray")):
            self.cards[key].grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))

        progress_panel = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        progress_panel.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 12))
        progress_panel.grid_columnconfigure(0, weight=1)
        self.progress_text = ctk.StringVar(value="Sin ejecucion")
        ctk.CTkLabel(progress_panel, textvariable=self.progress_text, font=("Segoe UI", 13), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 4)
        )
        self.progress = ctk.CTkProgressBar(progress_panel, height=8, progress_color=LEROY)
        self.progress.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))
        self.progress.set(0)

        table_panel = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        table_panel.grid(row=3, column=0, sticky="nsew", padx=28, pady=(0, 24))
        table_panel.grid_rowconfigure(1, weight=1)
        table_panel.grid_columnconfigure(0, weight=1)

        table_toolbar = ctk.CTkFrame(table_panel, fg_color="transparent")
        table_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 0))
        table_toolbar.grid_columnconfigure(0, weight=1)
        self.results_title_var = ctk.StringVar(value="Resultados")
        ctk.CTkLabel(table_toolbar, textvariable=self.results_title_var, font=("Segoe UI", 13, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkButton(
            table_toolbar,
            text="Todos",
            width=78,
            height=30,
            fg_color="#FFFFFF",
            text_color=TEXT,
            hover_color="#F3F4F6",
            border_width=1,
            border_color=BORDER,
            command=lambda: self.set_filter(None),
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            table_toolbar,
            text="Copiar EAN",
            width=104,
            height=30,
            fg_color="#FFFFFF",
            text_color=TEXT,
            hover_color="#F3F4F6",
            border_width=1,
            border_color=BORDER,
            command=self.copy_selected_ean,
        ).grid(row=0, column=2, sticky="e")

        self.setup_tree_style()
        columns = ("light", "ean", "reference", "stock", "feed_price", "status", "seller", "market_price", "reason")
        self.tree = ttk.Treeview(table_panel, columns=columns, show="headings", selectmode="browse")
        headings = {
            "light": "",
            "ean": "EAN",
            "reference": "SKU/ref",
            "stock": "Stock",
            "feed_price": "Feed",
            "status": "Estado",
            "seller": "Seller",
            "market_price": "Leroy",
            "reason": "Motivo",
        }
        widths = {
            "light": 58,
            "ean": 128,
            "reference": 120,
            "stock": 76,
            "feed_price": 82,
            "status": 170,
            "seller": 170,
            "market_price": 82,
            "reason": 420,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], minwidth=50, anchor="w")
        self.tree.tag_configure("green", foreground="#0F5132")
        self.tree.tag_configure("yellow", foreground="#7A4B00")
        self.tree.tag_configure("red", foreground="#842029")
        self.tree.tag_configure("gray", foreground="#4B5563")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(14, 0), pady=14)
        scroll = ttk.Scrollbar(table_panel, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 14), pady=14)
        self.tree.bind("<Double-1>", self.open_selected_url)
        self.tree.bind("<Control-c>", self.copy_selected_ean)

    def setup_tree_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=34,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#F9FAFB",
            foreground=MUTED,
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", "#E7F3EC")], foreground=[("selected", TEXT)])

    def load_shoppingfeed_url(self) -> str:
        env_url = (
            os.environ.get("SHOPPINGFEED_CATALOG_URL", "").strip()
            or os.environ.get("SHOPPINGFEED_URL", "").strip()
        )
        if env_url:
            return env_url
        if LOCAL_SETTINGS_PATH.exists():
            try:
                data = json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return ""
            return str(data.get("shoppingfeed_url", "") or "").strip()
        return ""

    def add_single_ean(self):
        ean = self.ean_var.get().strip()
        if not ean:
            return
        self.products.append(InputProduct(ean=ean))
        self.add_pending_row(self.products[-1])
        self.ean_var.set("")
        self.progress_text.set(f"{len(self.products)} productos cargados")

    def load_live_catalog(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de cargar otro catalogo.")
            return
        if self.catalog_worker and self.catalog_worker.is_alive():
            return
        if not self.shoppingfeed_url:
            messagebox.showerror(
                "Shoppingfeed no configurado",
                "Configura SHOPPINGFEED_URL o local_settings.json con shoppingfeed_url.",
            )
            return
        self.progress.set(0)
        self.progress_text.set("Descargando catalogo vivo de Shoppingfeed...")
        self.catalog_worker = threading.Thread(target=self.download_live_catalog, daemon=True)
        self.catalog_worker.start()

    def download_live_catalog(self):
        try:
            self.events.put(("catalog_progress", "Descargando catalogo vivo de Shoppingfeed..."))
            request = urllib.request.Request(
                self.shoppingfeed_url,
                headers={
                    "User-Agent": "OfferChecker/1.0",
                    "Accept": "text/csv,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
            text = raw.decode("utf-8-sig", errors="replace")
            lines = text.splitlines()
            if not lines or "ean" not in lines[0].casefold():
                raise ValueError("El feed no parece tener cabecera EAN.")
            self.events.put(("catalog_progress", "Catalogo descargado. Leyendo CSV..."))
            SHOPPINGFEED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            SHOPPINGFEED_CACHE_PATH.write_text(text, encoding="utf-8")
            products = read_products_csv(SHOPPINGFEED_CACHE_PATH)
            if not products:
                raise ValueError("No se encontraron EANs en el feed.")
            self.events.put(("catalog_loaded", products, str(SHOPPINGFEED_CACHE_PATH)))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            self.events.put(("catalog_error", str(exc)))

    def add_pending_row(self, product: InputProduct):
        item = self.tree.insert(
            "",
            "end",
            values=("", product.ean, product.reference, product.quantity, product.price, "Pendiente", "", "", ""),
        )
        self.row_items[product.ean] = item
        self.row_lights[item] = "pending"
        self.row_order.append(item)
        if self.active_filter is not None:
            self.tree.detach(item)
        return item

    def build_feed_stock_result(self, product: InputProduct) -> DashboardResult:
        return DashboardResult(
            ean=product.ean,
            reference=product.reference,
            feed_quantity=product.quantity,
            feed_price=product.price,
            light="red",
            status="SIN_STOCK_FEED",
            final_url=f"https://www.leroymerlin.es/search?q={product.ean}",
            title="",
            sku="",
            seller_name="",
            marketplace_price="",
            product_availability="feed_stock_zero",
            offer_available=False,
            buybox_ok="unknown",
            challenge_detected=False,
            reason="stock feed <= 0; no se abre Leroy",
            elapsed_seconds=0.0,
            html_path="",
        )

    def render_result_row(self, row: DashboardResult):
        item = self.row_items.get(row.ean)
        if not item:
            item = self.tree.insert("", "end")
            self.row_items[row.ean] = item
            self.row_order.append(item)
        code, _label, _color = LIGHT_META.get(row.light, LIGHT_META["gray"])
        self.tree.item(
            item,
            values=(
                code,
                row.ean,
                row.reference,
                row.feed_quantity,
                row.feed_price,
                self.business_status(row.status),
                row.seller_name,
                row.marketplace_price,
                row.reason,
            ),
            tags=(row.light,),
        )
        self.row_urls[item] = row.final_url
        self.row_lights[item] = row.light
        if row.light in self.counts:
            self.counts[row.light] += 1
            self.update_cards()
        if self.active_filter is not None and row.light != self.active_filter:
            self.tree.detach(item)
        elif self.active_filter is not None:
            self.tree.reattach(item, "", "end")

    def load_bulk(self):
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
        self.row_urls.clear()
        self.row_items.clear()
        self.row_lights.clear()
        self.row_order.clear()
        self.active_filter = None
        for product in self.products:
            self.add_pending_row(product)
        self.update_cards()
        self.progress.set(0)
        self.progress_text.set(f"{len(self.products)} productos cargados")

    def clear_list(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de limpiar la lista.")
            return
        self.products = []
        self.tree.delete(*self.tree.get_children())
        self.row_urls.clear()
        self.row_items.clear()
        self.row_lights.clear()
        self.row_order.clear()
        self.active_filter = None
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        self.update_cards()
        self.progress.set(0)
        self.progress_text.set("Lista limpia")

    def clean_profile(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de limpiar el perfil.")
            return
        if PROFILE_DIR.exists():
            shutil.rmtree(PROFILE_DIR)
        self.progress_text.set("Perfil dedicado limpiado")

    def start_analysis(self):
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
        try:
            cache_ttl = float(self.cache_ttl_var.get().replace(",", "."))
        except ValueError:
            cache_ttl = 24.0
        try:
            nav_timeout = float(self.nav_timeout_var.get().replace(",", "."))
        except ValueError:
            nav_timeout = 18.0
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        self.update_cards()
        self.tree.delete(*self.tree.get_children())
        self.row_urls.clear()
        self.row_items.clear()
        self.row_lights.clear()
        self.row_order.clear()
        self.cached_count = 0
        self.direct_count = 0
        products_to_check: list[InputProduct] = []
        expected_seller = self.expected_seller_var.get()
        offer_cache = OfferCache()
        for product in self.products:
            feed_qty = parse_quantity(product.quantity)
            if feed_qty is not None and feed_qty <= 0:
                self.add_pending_row(product)
                self.render_result_row(self.build_feed_stock_result(product))
                self.direct_count += 1
                continue
            cached_row = None
            if self.use_cache_var.get():
                cached_row = offer_cache.get_fresh(product, expected_seller, cache_ttl)
            if cached_row:
                self.add_pending_row(product)
                self.render_result_row(cached_row)
                self.cached_count += 1
            else:
                products_to_check.append(product)
                self.add_pending_row(product)
        self.progress.set(0)
        self.live_total = len(products_to_check)
        if not products_to_check:
            resolved = self.cached_count + self.direct_count
            self.progress.set(1)
            self.progress_text.set(f"Terminado sin navegador: {resolved} resueltos por cache/feed")
            return
        self.checker = LeroyChecker(
            products_to_check,
            expected_seller,
            delay,
            nav_timeout=nav_timeout,
            retry_timeout=max(nav_timeout * 2, 30.0),
            block_assets=self.block_assets_var.get(),
        )
        self.worker = threading.Thread(target=self.checker.run, args=(self.events,), daemon=True)
        self.worker.start()
        skipped = self.cached_count + self.direct_count
        self.progress_text.set(f"Analizando {self.live_total}; saltados {skipped} por cache/feed")

    def stop_analysis(self):
        if self.checker:
            self.checker.stop()
            self.progress_text.set("Parando al finalizar el producto actual...")

    def update_cards(self):
        for key, card in self.cards.items():
            card.set_value(self.counts[key])
            card.set_active(self.active_filter == key)
        self.update_filter_title()

    def set_filter(self, light: str | None):
        self.active_filter = None if self.active_filter == light else light
        self.apply_filter()
        self.update_cards()

    def update_filter_title(self):
        if not hasattr(self, "results_title_var"):
            return
        if not self.active_filter:
            self.results_title_var.set("Resultados")
            return
        _code, label, _color = LIGHT_META.get(self.active_filter, LIGHT_META["gray"])
        visible = sum(1 for item in self.row_order if self.row_lights.get(item) == self.active_filter)
        self.results_title_var.set(f"Resultados - {label} ({visible})")

    def apply_filter(self):
        for item in self.row_order:
            light = self.row_lights.get(item, "pending")
            should_show = self.active_filter is None or light == self.active_filter
            try:
                self.tree.detach(item)
            except Exception:
                continue
            if should_show:
                self.tree.reattach(item, "", "end")
        self.update_filter_title()

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "result":
                    _, index, total, row = event
                    self.render_result_row(row)
                    resolved = self.cached_count + self.direct_count + index
                    full_total = self.cached_count + self.direct_count + total
                    self.progress.set(resolved / full_total if full_total else 0)
                    self.progress_text.set(f"{resolved}/{full_total} resueltos ({index}/{total} navegador)")
                elif kind == "done":
                    _, elapsed, summary = event
                    skipped = self.cached_count + self.direct_count
                    self.progress_text.set(f"Terminado en {elapsed}s - {summary} - saltados {skipped}")
                elif kind == "run_dir":
                    self.subtitle_var.set(f"Salida: {event[1]}")
                elif kind == "error":
                    messagebox.showerror("Error", event[1])
                elif kind == "catalog_progress":
                    self.progress_text.set(event[1])
                elif kind == "catalog_loaded":
                    _, products, cache_path = event
                    self.products = products
                    self.tree.delete(*self.tree.get_children())
                    self.row_urls.clear()
                    self.row_items.clear()
                    self.row_lights.clear()
                    self.row_order.clear()
                    self.active_filter = None
                    self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
                    self.update_cards()
                    for product in self.products:
                        self.add_pending_row(product)
                    self.progress.set(0)
                    self.progress_text.set(f"{len(self.products)} productos cargados desde Shoppingfeed")
                    self.subtitle_var.set(f"Catalogo vivo cacheado en {cache_path}")
                elif kind == "catalog_error":
                    self.progress.set(0)
                    self.progress_text.set("Error descargando Shoppingfeed")
                    messagebox.showerror("Error Shoppingfeed", event[1])
        except queue.Empty:
            pass
        self.after(200, self.process_events)

    def business_status(self, status: str) -> str:
        return {
            "OK": "Correcto",
            "NO_DISPONIBLE_CON_STOCK": "No disponible con stock",
            "BUYBOX_PERDIDA": "Buybox perdida",
            "SIN_STOCK_FEED": "Sin stock feed",
            "NO_VIVA": "Fuera del marketplace",
            "NO_ENCONTRADA_PRELIMINAR": "No encontrada",
            "INCIERTA": "Reintentar",
        }.get(status, status)

    def open_selected_url(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        url = self.row_urls.get(selected[0])
        if url:
            webbrowser.open(url)

    def copy_selected_ean(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        if len(values) < 2:
            return
        ean = str(values[1]).strip()
        if not ean:
            return
        self.clipboard_clear()
        self.clipboard_append(ean)
        self.progress_text.set(f"EAN copiado: {ean}")
        return "break"


def main():
    app = ModernDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
