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
    OfferCache,
    PROFILE_DIR,
    create_checker,
    parse_quantity,
    read_products_csv,
)
from marketplaces import (
    MARKETPLACE_LABELS,
    build_marketplace_search_url,
    get_feed_cache_path,
    get_marketplace_config,
    get_marketplace_feed_url,
    get_offer_cache_path,
    marketplace_key_from_label,
)


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
        self.result = MARKETPLACE_LABELS[0]
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
        self.combo = ctk.CTkComboBox(box, values=MARKETPLACE_LABELS, state="readonly", height=38)
        self.combo.set(self.result)
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
    def __init__(self, master, label: str, color: str, command=None, retry_command=None):
        super().__init__(master, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
        self.color = color
        self.command = command
        self.retry_command = retry_command
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
        self.retry_button = ctk.CTkButton(
            content,
            text="Reintentar",
            height=24,
            width=92,
            fg_color="#FFFFFF",
            text_color=TEXT,
            hover_color="#F3F4F6",
            border_width=1,
            border_color=BORDER,
            command=self._retry_clicked,
        )
        self.retry_button.pack(anchor="w", pady=(8, 0))
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

    def _retry_clicked(self):
        if self.retry_command:
            self.retry_command()


class ModernDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")
        self.title("Nass Offer Checker")
        self.geometry("1360x820")
        self.minsize(1180, 720)
        self.configure(fg_color=APP_BG)

        self.events: queue.Queue = queue.Queue()
        self.products: list[InputProduct] = []
        self.checker = None
        self.worker: threading.Thread | None = None
        self.catalog_worker: threading.Thread | None = None
        self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
        self.row_urls: dict[str, str] = {}
        self.row_items: dict[str, str] = {}
        self.row_lights: dict[str, str] = {}
        self.row_statuses: dict[str, str] = {}
        self.row_order: list[str] = []
        self.active_filter: str | None = None
        self.active_status_filter: str | None = None
        self.force_live_once = False
        self.retrying_light: str | None = None
        self.worker_chips: dict[int, ctk.CTkLabel] = {}
        self.worker_meta: dict[int, dict[str, object]] = {}
        self.cached_count = 0
        self.direct_count = 0
        self.live_total = 0
        dialog = MarketplaceDialog(self)
        self.wait_window(dialog)
        self.marketplace = dialog.result
        self.marketplace_key = marketplace_key_from_label(self.marketplace)
        self.marketplace_config = get_marketplace_config(self.marketplace_key)
        self.shoppingfeed_url = self.load_marketplace_feed_url()

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
        self.brand_label = ctk.CTkLabel(
            badge,
            text="\n".join(self.marketplace_config.brand_lines),
            text_color="white",
            font=("Segoe UI", 20, "bold"),
        )
        self.brand_label.pack(
            expand=True
        )

        ctk.CTkLabel(sidebar, text="Marketplace", text_color="#B7D7C3", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=24, pady=(8, 6)
        )
        self.marketplace_box = ctk.CTkComboBox(
            sidebar,
            values=MARKETPLACE_LABELS,
            state="readonly",
            height=38,
            command=self.change_marketplace,
        )
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
            text="Modo datos minimos",
            variable=self.block_assets_var,
            text_color="#D9F0E0",
            fg_color=LEROY,
            hover_color="#114D30",
        ).pack(anchor="w", padx=22, pady=(0, 10))
        self.data_settle_var = ctk.StringVar(value="700")
        ctk.CTkEntry(sidebar, textvariable=self.data_settle_var, placeholder_text="Render ms", height=38).pack(
            fill="x", padx=22
        )

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
            "green": MetricCard(
                metrics,
                "Correctos",
                GREEN,
                command=lambda: self.set_filter("green"),
                retry_command=lambda: self.retry_light("green"),
            ),
            "yellow": MetricCard(
                metrics,
                "Revisar",
                YELLOW,
                command=lambda: self.set_filter("yellow"),
                retry_command=lambda: self.retry_light("yellow"),
            ),
            "red": MetricCard(
                metrics,
                "Fuera",
                RED,
                command=lambda: self.set_filter("red"),
                retry_command=lambda: self.retry_light("red"),
            ),
            "gray": MetricCard(
                metrics,
                "Tecnico",
                GRAY,
                command=lambda: self.set_filter("gray"),
                retry_command=lambda: self.retry_light("gray"),
            ),
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
        phase3_controls = ctk.CTkFrame(progress_panel, fg_color="transparent")
        phase3_controls.grid(row=0, column=1, sticky="e", padx=18, pady=(10, 0))
        ctk.CTkLabel(phase3_controls, text="Workers", text_color=MUTED, font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
        self.worker_count_var = ctk.StringVar(value="1")
        ctk.CTkEntry(phase3_controls, textvariable=self.worker_count_var, width=48, height=28).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(phase3_controls, text="Corte tecnico", text_color=MUTED, font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
        self.circuit_threshold_var = ctk.StringVar(value="4")
        ctk.CTkEntry(phase3_controls, textvariable=self.circuit_threshold_var, width=48, height=28).pack(side="left")
        self.progress = ctk.CTkProgressBar(progress_panel, height=8, progress_color=LEROY)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 14))
        self.progress.set(0)
        self.worker_summary_var = ctk.StringVar(value="Workers sin iniciar")
        ctk.CTkLabel(
            progress_panel,
            textvariable=self.worker_summary_var,
            font=("Segoe UI", 11),
            text_color=MUTED,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 6))
        self.worker_status_panel = ctk.CTkFrame(progress_panel, fg_color="transparent")
        self.worker_status_panel.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 14))
        for col in range(5):
            self.worker_status_panel.grid_columnconfigure(col, weight=1)
        self.reset_worker_chips(1)

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
        self.subfilter_frame = ctk.CTkFrame(table_toolbar, fg_color="transparent")
        self.subfilter_frame.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.subfilter_buttons = {
            "NO_VIVA": ctk.CTkButton(
                self.subfilter_frame,
                text="Fuera marketplace",
                width=136,
                height=30,
                fg_color="#FFFFFF",
                text_color=TEXT,
                hover_color="#F3F4F6",
                border_width=1,
                border_color=BORDER,
                command=lambda: self.set_status_filter("NO_VIVA"),
            ),
            "SIN_STOCK_FEED": ctk.CTkButton(
                self.subfilter_frame,
                text="Sin stock feed",
                width=118,
                height=30,
                fg_color="#FFFFFF",
                text_color=TEXT,
                hover_color="#F3F4F6",
                border_width=1,
                border_color=BORDER,
                command=lambda: self.set_status_filter("SIN_STOCK_FEED"),
            ),
        }
        self.subfilter_buttons["NO_VIVA"].pack(side="left", padx=(0, 6))
        self.subfilter_buttons["SIN_STOCK_FEED"].pack(side="left")
        self.subfilter_buttons["NO_VIVA"].pack_forget()
        self.subfilter_buttons["SIN_STOCK_FEED"].pack_forget()
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
            command=self.clear_filters,
        ).grid(row=0, column=2, sticky="e", padx=(0, 8))
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
        ).grid(row=0, column=3, sticky="e")

        self.setup_tree_style()
        columns = ("light", "ean", "reference", "product", "stock", "feed_price", "status", "seller", "market_price", "reason")
        self.tree = ttk.Treeview(table_panel, columns=columns, show="headings", selectmode="browse")
        headings = {
            "light": "",
            "ean": "EAN",
            "reference": "SKU/ref",
            "product": "Producto",
            "stock": "Stock",
            "feed_price": "Feed",
            "status": "Estado",
            "seller": "Seller",
            "market_price": "Market",
            "reason": "Motivo",
        }
        widths = {
            "light": 58,
            "ean": 128,
            "reference": 120,
            "product": 260,
            "stock": 76,
            "feed_price": 82,
            "status": 150,
            "seller": 140,
            "market_price": 82,
            "reason": 320,
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

    def load_marketplace_feed_url(self) -> str:
        return get_marketplace_feed_url(self.marketplace_key)

    def change_marketplace(self, label: str):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de cambiar marketplace.")
            self.marketplace_box.set(self.marketplace)
            return
        self.marketplace = label
        self.marketplace_key = marketplace_key_from_label(label)
        self.marketplace_config = get_marketplace_config(self.marketplace_key)
        self.shoppingfeed_url = self.load_marketplace_feed_url()
        self.brand_label.configure(text="\n".join(self.marketplace_config.brand_lines))
        self.clear_list()
        self.subtitle_var.set(f"Marketplace activo: {self.marketplace}")

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
                f"Configura el feed de {self.marketplace} en local_settings.json o variable de entorno.",
            )
            return
        self.progress.set(0)
        self.progress_text.set(f"Descargando catalogo vivo de {self.marketplace}...")
        self.catalog_worker = threading.Thread(target=self.download_live_catalog, daemon=True)
        self.catalog_worker.start()

    def download_live_catalog(self):
        try:
            self.events.put(("catalog_progress", f"Descargando catalogo vivo de {self.marketplace}..."))
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
            cache_path = get_feed_cache_path(self.marketplace_key)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
            products = read_products_csv(cache_path)
            if not products:
                raise ValueError("No se encontraron EANs en el feed.")
            self.events.put(("catalog_loaded", products, str(cache_path)))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            self.events.put(("catalog_error", str(exc)))

    def add_pending_row(self, product: InputProduct):
        item = self.tree.insert(
            "",
            "end",
            values=("", product.ean, product.reference, "", product.quantity, product.price, "Pendiente", "", "", ""),
        )
        self.row_items[product.ean] = item
        self.row_lights[item] = "pending"
        self.row_statuses[item] = "PENDIENTE"
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
            final_url=build_marketplace_search_url(self.marketplace_key, [product.ean]),
            title="",
            sku="",
            seller_name="",
            marketplace_price="",
            product_availability="feed_stock_zero",
            offer_available=False,
            buybox_ok="unknown",
            challenge_detected=False,
            reason=f"stock feed <= 0; no se abre {self.marketplace}",
            elapsed_seconds=0.0,
            html_path="",
        )

    def render_result_row(self, row: DashboardResult):
        item = self.row_items.get(row.ean)
        if not item:
            item = self.tree.insert("", "end")
            self.row_items[row.ean] = item
            self.row_order.append(item)
        previous_light = self.row_lights.get(item)
        if previous_light in self.counts:
            self.counts[previous_light] = max(0, self.counts[previous_light] - 1)
        code, _label, _color = LIGHT_META.get(row.light, LIGHT_META["gray"])
        self.tree.item(
            item,
            values=(
                code,
                row.ean,
                row.reference,
                row.title,
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
        self.row_statuses[item] = row.status
        if row.light in self.counts:
            self.counts[row.light] += 1
            self.update_cards()
        if not self.item_matches_filters(item):
            self.tree.detach(item)
        elif self.active_filter is not None or self.active_status_filter is not None:
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
        self.row_statuses.clear()
        self.row_order.clear()
        self.active_filter = None
        self.active_status_filter = None
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
        self.row_statuses.clear()
        self.row_order.clear()
        self.active_filter = None
        self.active_status_filter = None
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

    def product_from_item(self, item: str) -> InputProduct | None:
        values = self.tree.item(item, "values")
        if len(values) < 5:
            return None
        ean = str(values[1]).strip()
        if not ean:
            return None
        return InputProduct(
            ean=ean,
            reference=str(values[2]).strip(),
            quantity=str(values[4]).strip(),
            price=str(values[5]).strip(),
        )

    def retry_light(self, light: str):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecucion", "Para el analisis antes de reintentar.")
            return
        products: list[InputProduct] = []
        seen: set[str] = set()
        for item in self.row_order:
            if self.row_lights.get(item) != light:
                continue
            product = self.product_from_item(item)
            if product and product.ean not in seen:
                products.append(product)
                seen.add(product.ean)
        if not products:
            _code, label, _color = LIGHT_META.get(light, LIGHT_META["gray"])
            self.progress_text.set(f"No hay EAN para reintentar en {label}")
            return
        self.products = products
        self.force_live_once = True
        self.retrying_light = light
        _code, label, _color = LIGHT_META.get(light, LIGHT_META["gray"])
        self.progress_text.set(f"Reintentando {len(products)} EAN de {label}")
        self.start_analysis()

    def start_analysis(self):
        if not self.products:
            self.add_single_ean()
        if not self.products:
            messagebox.showwarning("Sin productos", "Agrega un EAN o carga un CSV.")
            return
        if self.worker and self.worker.is_alive():
            self.progress_text.set("Ya hay un analisis activo; pulsa Parar antes de lanzar otro.")
            return
        self.events = queue.Queue()
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
        try:
            data_settle_ms = int(float(self.data_settle_var.get().replace(",", ".")))
        except ValueError:
            data_settle_ms = 700
        data_settle_ms = max(0, min(data_settle_ms, 3000))
        self.data_settle_var.set(str(data_settle_ms))
        try:
            worker_count = int(float(self.worker_count_var.get().replace(",", ".")))
        except ValueError:
            worker_count = 1
        worker_count = max(1, min(worker_count, 10))
        self.worker_count_var.set(str(worker_count))
        self.reset_worker_chips(worker_count)
        try:
            circuit_threshold = int(float(self.circuit_threshold_var.get().replace(",", ".")))
        except ValueError:
            circuit_threshold = 4
        circuit_threshold = max(1, min(circuit_threshold, 10))
        self.circuit_threshold_var.set(str(circuit_threshold))
        retrying_light = self.retrying_light
        self.retrying_light = None
        if retrying_light:
            for product in self.products:
                item = self.row_items.get(product.ean)
                if not item:
                    continue
                old_light = self.row_lights.get(item)
                if old_light in self.counts:
                    self.counts[old_light] = max(0, self.counts[old_light] - 1)
                self.tree.item(
                    item,
                    values=("", product.ean, product.reference, "", product.quantity, product.price, "Pendiente", "", "", ""),
                    tags=(),
                )
                self.row_lights[item] = "pending"
                self.row_statuses[item] = "PENDIENTE"
                self.row_urls[item] = ""
                if self.active_filter is not None:
                    self.tree.detach(item)
            self.update_cards()
        else:
            self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
            self.update_cards()
            self.tree.delete(*self.tree.get_children())
            self.row_urls.clear()
            self.row_items.clear()
            self.row_lights.clear()
            self.row_statuses.clear()
            self.row_order.clear()
        self.cached_count = 0
        self.direct_count = 0
        bypass_cache = self.force_live_once
        self.force_live_once = False
        products_to_check: list[InputProduct] = []
        expected_seller = self.expected_seller_var.get()
        offer_cache = OfferCache(get_offer_cache_path(self.marketplace_key))
        for product in self.products:
            feed_qty = parse_quantity(product.quantity)
            if feed_qty is not None and feed_qty <= 0:
                self.add_pending_row(product)
                self.render_result_row(self.build_feed_stock_result(product))
                self.direct_count += 1
                continue
            cached_row = None
            if self.use_cache_var.get() and not bypass_cache:
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
        self.checker = create_checker(
            self.marketplace_key,
            products_to_check,
            expected_seller,
            delay,
            nav_timeout=nav_timeout,
            retry_timeout=max(nav_timeout * 2, 30.0),
            block_assets=self.block_assets_var.get(),
            minimal_data_mode=self.block_assets_var.get(),
            data_settle_ms=data_settle_ms,
            worker_count=worker_count,
            circuit_breaker_threshold=circuit_threshold,
            cache_path=get_offer_cache_path(self.marketplace_key),
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
        self.update_subfilter_buttons()

    def reset_worker_chips(self, count: int):
        if not hasattr(self, "worker_status_panel"):
            return
        for child in self.worker_status_panel.winfo_children():
            child.destroy()
        self.worker_chips.clear()
        self.worker_meta.clear()
        for worker_id in range(1, max(1, min(count, 10)) + 1):
            chip = ctk.CTkLabel(
                self.worker_status_panel,
                text=f"W{worker_id} pendiente | P:no | UA:def",
                fg_color="#F3F4F6",
                text_color=MUTED,
                corner_radius=8,
                height=26,
                font=("Segoe UI", 10),
            )
            chip.grid(row=(worker_id - 1) // 5, column=(worker_id - 1) % 5, sticky="ew", padx=(0, 8), pady=(0, 6))
            self.worker_chips[worker_id] = chip
            self.worker_meta[worker_id] = {
                "enabled": True,
                "proxy": False,
                "ua": False,
                "status": "pendiente",
            }
        self.update_worker_summary()

    def update_worker_summary(self):
        if not hasattr(self, "worker_summary_var"):
            return
        if not self.worker_meta:
            self.worker_summary_var.set("Workers sin iniciar")
            return

        statuses = [str(meta.get("status", "pendiente")) for meta in self.worker_meta.values()]
        active = statuses.count("activo")
        paused = statuses.count("pausado")
        warming = statuses.count("calentando")
        blocked = statuses.count("bloqueado")
        closed = statuses.count("cerrado")
        disabled = sum(1 for meta in self.worker_meta.values() if not bool(meta.get("enabled", True)))
        pending = statuses.count("pendiente")
        proxies = sum(1 for meta in self.worker_meta.values() if meta.get("proxy"))
        user_agents = sum(1 for meta in self.worker_meta.values() if meta.get("ua"))
        total = len(self.worker_meta)

        parts = [f"{active}/{total} workers activos"]
        if pending:
            parts.append(f"{pending} pendientes")
        if warming:
            parts.append(f"{warming} calentando")
        if paused:
            parts.append(f"{paused} pausados")
        if blocked:
            parts.append(f"{blocked} bloqueados")
        if closed:
            parts.append(f"{closed} cerrados")
        if disabled:
            parts.append(f"{disabled} desactivados")
        parts.append(f"Proxy {proxies}/{total}")
        parts.append(f"UA {user_agents}/{total}")
        self.worker_summary_var.set(" | ".join(parts))

    def update_worker_chip(
        self,
        worker_id: int,
        status: str | None = None,
        enabled: bool | None = None,
        proxy_configured: bool | None = None,
        user_agent_configured: bool | None = None,
    ):
        if worker_id not in self.worker_chips:
            return
        meta = self.worker_meta.setdefault(worker_id, {})
        if status is not None:
            meta["status"] = status
        if enabled is not None:
            meta["enabled"] = enabled
        if proxy_configured is not None:
            meta["proxy"] = proxy_configured
        if user_agent_configured is not None:
            meta["ua"] = user_agent_configured

        current_status = str(meta.get("status", "pendiente"))
        proxy = "si" if meta.get("proxy") else "no"
        ua = "custom" if meta.get("ua") else "def"
        enabled_now = bool(meta.get("enabled", True))
        colors = {
            "pendiente": ("#F3F4F6", MUTED),
            "calentando": ("#DBEAFE", "#1D4ED8"),
            "activo": ("#DCFCE7", "#166534"),
            "cerrado": ("#E5E7EB", "#4B5563"),
            "desactivado": ("#F3F4F6", "#98A2B3"),
            "bloqueado": ("#FEE2E2", "#991B1B"),
            "pausado": ("#FEF3C7", "#92400E"),
            "pendiente challenge": ("#FEF3C7", "#92400E"),
            "error": ("#FEE2E2", "#991B1B"),
        }
        if not enabled_now:
            current_status = "desactivado"
        fg, text_color = colors.get(current_status, ("#F3F4F6", MUTED))
        self.worker_chips[worker_id].configure(
            text=f"W{worker_id} {current_status} | P:{proxy} | UA:{ua}",
            fg_color=fg,
            text_color=text_color,
        )
        self.update_worker_summary()

    def set_filter(self, light: str | None):
        self.active_filter = None if self.active_filter == light else light
        if self.active_filter != "red":
            self.active_status_filter = None
        self.apply_filter()
        self.update_cards()
        self.update_subfilter_buttons()

    def clear_filters(self):
        self.active_filter = None
        self.active_status_filter = None
        self.apply_filter()
        self.update_cards()
        self.update_subfilter_buttons()

    def set_status_filter(self, status: str | None):
        self.active_filter = "red"
        self.active_status_filter = None if self.active_status_filter == status else status
        self.apply_filter()
        self.update_cards()
        self.update_subfilter_buttons()

    def update_filter_title(self):
        if not hasattr(self, "results_title_var"):
            return
        if not self.active_filter:
            self.results_title_var.set("Resultados")
            return
        _code, label, _color = LIGHT_META.get(self.active_filter, LIGHT_META["gray"])
        visible = sum(1 for item in self.row_order if self.item_matches_filters(item))
        if self.active_status_filter:
            label = self.business_status(self.active_status_filter)
        self.results_title_var.set(f"Resultados - {label} ({visible})")

    def item_matches_filters(self, item: str) -> bool:
        light = self.row_lights.get(item, "pending")
        status = self.row_statuses.get(item, "")
        if self.active_filter is not None and light != self.active_filter:
            return False
        if self.active_status_filter is not None and status != self.active_status_filter:
            return False
        return True

    def update_subfilter_buttons(self):
        if not hasattr(self, "subfilter_buttons"):
            return
        visible = self.active_filter == "red"
        for status, button in self.subfilter_buttons.items():
            if visible:
                count = sum(1 for item in self.row_order if self.row_statuses.get(item) == status)
                active = self.active_status_filter == status
                button.configure(
                    text=f"{self.business_status(status)} ({count})",
                    fg_color="#FEE2E2" if active else "#FFFFFF",
                    border_color=RED if active else BORDER,
                    text_color=RED if active else TEXT,
                )
                button.pack(side="left", padx=(0, 6) if status == "NO_VIVA" else 0)
            else:
                button.pack_forget()

    def apply_filter(self):
        for item in self.row_order:
            should_show = self.item_matches_filters(item)
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
                elif kind == "phase3":
                    self.progress_text.set(f"Fase 3 activa: {event[1]} worker(s), corte tecnico {event[2]}")
                elif kind == "worker_config":
                    self.update_worker_chip(
                        event[1],
                        enabled=event[2],
                        proxy_configured=event[3],
                        user_agent_configured=event[4],
                    )
                elif kind == "worker_status":
                    self.update_worker_chip(event[1], status=event[2])
                elif kind == "circuit_breaker":
                    for worker_id in self.worker_chips:
                        status = self.worker_meta.get(worker_id, {}).get("status")
                        if status == "activo":
                            self.update_worker_chip(worker_id, status="pausado")
                    self.progress_text.set(f"Corte tecnico activado tras {event[3]} senales: EAN {event[1]}")
                elif kind == "worker_blocked":
                    self.progress_text.set(f"Worker {event[1]} bloqueado: {event[2]}")
                elif kind == "human_challenge_required":
                    self.update_worker_chip(event[1], status="pendiente challenge")
                    self.progress_text.set(f"Worten requiere resolver challenge manualmente en Worker {event[1]}")
                elif kind == "human_challenge_resolved":
                    self.update_worker_chip(event[1], status="activo")
                    self.progress_text.set(f"Challenge resuelto en Worker {event[1]}; continuando")
                elif kind == "human_challenge_timeout":
                    self.update_worker_chip(event[1], status="bloqueado")
                    self.progress_text.set(f"No se resolvio el challenge en Worker {event[1]}")
                elif kind == "error":
                    messagebox.showerror("Error", event[1])
                elif kind == "alert_sent":
                    self.progress_text.set(f"Alerta enviada a Slack: EAN {event[1]} ({event[2]})")
                elif kind == "catalog_progress":
                    self.progress_text.set(event[1])
                elif kind == "catalog_loaded":
                    _, products, cache_path = event
                    self.products = products
                    self.tree.delete(*self.tree.get_children())
                    self.row_urls.clear()
                    self.row_items.clear()
                    self.row_lights.clear()
                    self.row_statuses.clear()
                    self.row_order.clear()
                    self.active_filter = None
                    self.active_status_filter = None
                    self.counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
                    self.update_cards()
                    for product in self.products:
                        self.add_pending_row(product)
                    self.progress.set(0)
                    self.progress_text.set(f"{len(self.products)} productos cargados desde {self.marketplace}")
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
            "ENCONTRADO_PENDIENTE_DETALLE": "Encontrado, revisar detalle",
            "WORTEN_LOGICA_PENDIENTE": "Worten pendiente",
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
