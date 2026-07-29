import argparse
import csv
import getpass
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


BASE_SEARCH_URL = "https://www.leroymerlin.es/search"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
COOKIE_ENV = "LEROY_COOKIE_HEADER"
USER_AGENT_ENV = "LEROY_USER_AGENT"


@dataclass
class CheckResult:
    ean: str
    preliminary_status: str
    http_status: int | str
    final_url: str
    html_path: str
    html_bytes: int
    ean_in_html: bool
    candidate_count: int
    first_candidate_url: str
    session_mode: str
    cookie_fingerprint: str
    challenge_type: str
    diagnostics_path: str
    reason: str


def read_eans(path: Path) -> list[str]:
    for delimiter in (";", ","):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            if reader.fieldnames and "ean" in reader.fieldnames:
                return [row["ean"].strip() for row in reader if row.get("ean", "").strip()]
    raise ValueError(f"No ean column found in {path}")


def build_search_url(ean: str) -> str:
    return BASE_SEARCH_URL + "?" + urllib.parse.urlencode({"q": ean})


def clean_header_value(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("Header values cannot contain newlines")
    return value.strip()


def build_headers(cookie_header: str, user_agent: str) -> dict[str, str]:
    headers = {
        "User-Agent": clean_header_value(user_agent),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.leroymerlin.es/",
        "Upgrade-Insecure-Requests": "1",
    }
    if cookie_header:
        headers["Cookie"] = clean_header_value(cookie_header)
    return headers


def fetch(url: str, timeout: int, cookie_header: str, user_agent: str) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers=build_headers(cookie_header, user_agent),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.geturl(), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.geturl(), exc.read()


def looks_blocked(status: int | str, body: bytes) -> bool:
    if status in (401, 403, 407, 408, 409, 423, 429, 503):
        return True
    text = body[:200_000].decode("utf-8", errors="ignore").lower()
    blocked_markers = [
        "captcha",
        "datadome",
        "access denied",
        "forbidden",
        "robot",
        "challenge",
        "unusual traffic",
    ]
    return any(marker in text for marker in blocked_markers)


def diagnose_response(status: int | str, body: bytes, candidates: list[str]) -> dict[str, object]:
    text = body[:300_000].decode("utf-8", errors="ignore")
    lowered = text.lower()
    markers = {
        "datadome_var": "var dd=" in lowered or "var dd =" in lowered,
        "captcha_delivery": "captcha-delivery.com" in lowered,
        "please_enable_js": "please enable js" in lowered,
        "captcha": "captcha" in lowered,
        "access_denied": "access denied" in lowered,
        "product_url_present": bool(candidates),
        "json_ld_present": "application/ld+json" in lowered,
        "next_data_present": "__next_data__" in lowered,
    }
    challenge_type = "none"
    if markers["datadome_var"] or markers["captcha_delivery"]:
        challenge_type = "datadome_challenge"
    elif status in (401, 403, 407, 408, 409, 423, 429, 503):
        challenge_type = "http_block"
    elif len(body) < 10_000:
        challenge_type = "thin_html"

    return {
        "status": status,
        "html_bytes": len(body),
        "challenge_type": challenge_type,
        "markers": markers,
    }


def extract_candidate_urls(body: bytes) -> list[str]:
    text = body.decode("utf-8", errors="ignore")
    text = html.unescape(text)
    patterns = [
        r"https://www\.leroymerlin\.es/productos/[^\"'<>\\\s]+?\.html",
        r"/productos/[^\"'<>\\\s]+?\.html",
    ]
    candidates: list[str] = []
    seen = set()
    for pattern in patterns:
        for match in re.findall(pattern, text):
            url = match
            if url.startswith("/"):
                url = "https://www.leroymerlin.es" + url
            url = url.split("?")[0]
            if url not in seen:
                candidates.append(url)
                seen.add(url)
    return candidates


def classify(ean: str, status: int | str, body: bytes, candidates: list[str]) -> tuple[str, str]:
    if looks_blocked(status, body):
        return "INCIERTA", "bloqueo, captcha o error HTTP compatible con proteccion"
    if not isinstance(status, int) or status >= 500:
        return "INCIERTA", "error tecnico de servidor o red"
    if len(body) < 10_000:
        return "INCIERTA", "HTML demasiado pequeno para confiar en la ausencia"
    if ean.encode("utf-8") in body:
        return "VIVA_CANDIDATA", "el EAN aparece en el HTML de busqueda"
    if candidates:
        return "VIVA_CANDIDATA", "hay URLs candidatas de producto para validar en fase 2"
    return "NO_ENCONTRADA_PRELIMINAR", "busqueda correcta sin EAN ni candidatos de producto"


def write_csv(path: Path, rows: Iterable[CheckResult]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(asdict(rows[0]).keys()) if rows else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def check_ean(
    ean: str,
    output_dir: Path,
    timeout: int,
    cookie_header: str,
    user_agent: str,
) -> tuple[CheckResult, dict]:
    url = build_search_url(ean)
    session_mode = "cookie_env_http" if cookie_header else "anonymous_http"
    cookie_fingerprint = hashlib.sha256(cookie_header.encode("utf-8")).hexdigest()[:12] if cookie_header else ""
    try:
        status, final_url, body = fetch(url, timeout, cookie_header, user_agent)
    except Exception as exc:
        result = CheckResult(
            ean=ean,
            preliminary_status="INCIERTA",
            http_status="ERROR",
            final_url=url,
            html_path="",
            html_bytes=0,
            ean_in_html=False,
            candidate_count=0,
            first_candidate_url="",
            session_mode=session_mode,
            cookie_fingerprint=cookie_fingerprint,
            challenge_type="network_error",
            diagnostics_path="",
            reason=f"error de red: {exc}",
        )
        return result, {
            "ean": ean,
            "url": url,
            "session_mode": session_mode,
            "cookie_fingerprint": cookie_fingerprint,
            "error": str(exc),
        }

    html_dir = output_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    html_path = html_dir / f"{ean}_{digest}.html"
    html_path.write_bytes(body)

    candidates = extract_candidate_urls(body)
    diagnostics = diagnose_response(status, body, candidates)
    diagnostics_path = output_dir / f"{ean}_diagnostics.json"
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    preliminary_status, reason = classify(ean, status, body, candidates)
    result = CheckResult(
        ean=ean,
        preliminary_status=preliminary_status,
        http_status=status,
        final_url=final_url,
        html_path=str(html_path),
        html_bytes=len(body),
        ean_in_html=ean.encode("utf-8") in body,
        candidate_count=len(candidates),
        first_candidate_url=candidates[0] if candidates else "",
        session_mode=session_mode,
        cookie_fingerprint=cookie_fingerprint,
        challenge_type=str(diagnostics["challenge_type"]),
        diagnostics_path=str(diagnostics_path),
        reason=reason,
    )
    raw = {
        "ean": ean,
        "search_url": url,
        "session_mode": session_mode,
        "cookie_fingerprint": cookie_fingerprint,
        "http_status": status,
        "final_url": final_url,
        "html_path": str(html_path),
        "candidate_urls": candidates,
        "diagnostics_path": str(diagnostics_path),
        "diagnostics": diagnostics,
        "reason": reason,
    }
    return result, raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ean-file", type=Path, default=Path("Referencias.csv"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=8.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--cookie-prompt",
        action="store_true",
        help=f"Prompt for {COOKIE_ENV} without putting it in the shell history.",
    )
    args = parser.parse_args()

    cookie_header = ""
    if args.cookie_prompt:
        cookie_header = getpass.getpass("Cookie header for leroymerlin.es: ").strip()
    else:
        cookie_header = os.environ.get(COOKIE_ENV, "").strip()
    user_agent = os.environ.get(USER_AGENT_ENV, DEFAULT_USER_AGENT).strip()

    eans = read_eans(args.ean_file)
    if args.limit:
        eans = eans[: args.limit]
    if not eans:
        print("No EANs found", file=sys.stderr)
        return 2

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("fase1/output_local") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[CheckResult] = []
    raw_items = []
    if cookie_header:
        print(f"Using cookie header from {COOKIE_ENV}; cookie value will not be written to outputs.")
    for index, ean in enumerate(eans, start=1):
        print(f"[{index}/{len(eans)}] checking EAN {ean}")
        result, raw = check_ean(ean, output_dir, args.timeout, cookie_header, user_agent)
        results.append(result)
        raw_items.append(raw)
        if index < len(eans):
            time.sleep(args.delay)

    summary_path = output_dir / "summary.csv"
    raw_path = output_dir / "raw.json"
    write_csv(summary_path, results)
    raw_path.write_text(json.dumps(raw_items, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Summary: {summary_path}")
    print(f"Raw: {raw_path}")
    print(json.dumps([asdict(row) for row in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
