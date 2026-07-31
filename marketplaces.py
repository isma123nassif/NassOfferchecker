import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


BASE_DIR = Path(__file__).resolve().parent
FASE_DIR = BASE_DIR / "fase1"
LOCAL_SETTINGS_PATH = BASE_DIR / "local_settings.json"


@dataclass(frozen=True)
class MarketplaceConfig:
    key: str
    label: str
    brand_lines: tuple[str, ...]
    home_url: str
    search_batch_size: int
    feed_cache_filename: str
    offer_cache_filename: str
    env_vars: tuple[str, ...]
    legacy_settings_keys: tuple[str, ...] = ()


MARKETPLACES: dict[str, MarketplaceConfig] = {
    "leroy": MarketplaceConfig(
        key="leroy",
        label="Leroy Merlin",
        brand_lines=("LEROY", "MERLIN"),
        home_url="https://www.leroymerlin.es/",
        search_batch_size=1,
        feed_cache_filename="shoppingfeed_leroy_latest.csv",
        offer_cache_filename="offer_cache_leroy.sqlite",
        env_vars=("LEROY_SHOPPINGFEED_URL", "SHOPPINGFEED_CATALOG_URL", "SHOPPINGFEED_URL"),
        legacy_settings_keys=("shoppingfeed_url",),
    ),
    "carrefour": MarketplaceConfig(
        key="carrefour",
        label="Carrefour",
        brand_lines=("CARRE", "FOUR"),
        home_url="https://www.carrefour.es/",
        search_batch_size=7,
        feed_cache_filename="shoppingfeed_carrefour_latest.csv",
        offer_cache_filename="offer_cache_carrefour.sqlite",
        env_vars=("CARREFOUR_SHOPPINGFEED_URL",),
        legacy_settings_keys=("carrefour_shoppingfeed_url",),
    ),
    "worten": MarketplaceConfig(
        key="worten",
        label="Worten",
        brand_lines=("WORTEN",),
        home_url="https://www.worten.pt/",
        search_batch_size=10,
        feed_cache_filename="shoppingfeed_worten_latest.csv",
        offer_cache_filename="offer_cache_worten.sqlite",
        env_vars=("WORTEN_SHOPPINGFEED_URL",),
        legacy_settings_keys=("worten_shoppingfeed_url",),
    ),
    "conforama": MarketplaceConfig(
        key="conforama",
        label="Conforama",
        brand_lines=("CONFO", "RAMA"),
        home_url="https://www.conforama.es/",
        search_batch_size=1,
        feed_cache_filename="shoppingfeed_conforama_latest.csv",
        offer_cache_filename="offer_cache_conforama.sqlite",
        env_vars=("CONFORAMA_SHOPPINGFEED_URL", "LEROY_SHOPPINGFEED_URL", "SHOPPINGFEED_CATALOG_URL", "SHOPPINGFEED_URL"),
        legacy_settings_keys=("conforama_shoppingfeed_url", "shoppingfeed_url"),
    ),
}

MARKETPLACE_LABELS = [config.label for config in MARKETPLACES.values()]
LABEL_TO_KEY = {config.label: config.key for config in MARKETPLACES.values()}


def read_local_settings() -> dict:
    if not LOCAL_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def marketplace_key_from_label(label: str) -> str:
    return LABEL_TO_KEY.get(label, "leroy")


def get_marketplace_config(key_or_label: str) -> MarketplaceConfig:
    key = key_or_label if key_or_label in MARKETPLACES else marketplace_key_from_label(key_or_label)
    return MARKETPLACES.get(key, MARKETPLACES["leroy"])


def get_marketplace_feed_url(key_or_label: str) -> str:
    config = get_marketplace_config(key_or_label)
    for env_var in config.env_vars:
        value = os.environ.get(env_var, "").strip()
        if value:
            return value

    settings = read_local_settings()
    marketplaces = settings.get("marketplaces", {})
    if isinstance(marketplaces, dict):
        marketplace_settings = marketplaces.get(config.key, {})
        if isinstance(marketplace_settings, dict):
            value = str(marketplace_settings.get("shoppingfeed_url", "") or "").strip()
            if value:
                return value
        if config.key == "conforama":
            leroy_settings = marketplaces.get("leroy", {})
            if isinstance(leroy_settings, dict):
                value = str(leroy_settings.get("shoppingfeed_url", "") or "").strip()
                if value:
                    return value

    for legacy_key in config.legacy_settings_keys:
        value = str(settings.get(legacy_key, "") or "").strip()
        if value:
            return value
    return ""


def get_feed_cache_path(key_or_label: str) -> Path:
    config = get_marketplace_config(key_or_label)
    return FASE_DIR / config.feed_cache_filename


def get_offer_cache_path(key_or_label: str) -> Path:
    config = get_marketplace_config(key_or_label)
    return FASE_DIR / config.offer_cache_filename


def build_marketplace_search_url(key_or_label: str, eans: list[str]) -> str:
    config = get_marketplace_config(key_or_label)
    clean_eans = [ean.strip() for ean in eans if ean and ean.strip()]
    if config.key == "carrefour":
        query = quote(" ".join(clean_eans[: config.search_batch_size]))
        return f"https://www.carrefour.es/?query={query}"
    if config.key == "worten":
        query = quote(" ".join(clean_eans[: config.search_batch_size])) if clean_eans else "*"
        seller_id = "e5dae97c-401c-456a-be59-56a4f73b0bb5"
        return f"https://www.worten.pt/search?query={query}&facetFilters=seller_id:{seller_id}&utm_source=sellerpage_redirect"
    if config.key == "conforama":
        query = quote(clean_eans[0]) if clean_eans else ""
        return f"https://www.conforama.es/?query={query}"
    ean = quote(clean_eans[0]) if clean_eans else ""
    return f"https://www.leroymerlin.es/search?q={ean}"


def chunk_products(items: list, size: int) -> list[list]:
    size = max(1, int(size))
    return [items[index : index + size] for index in range(0, len(items), size)]
