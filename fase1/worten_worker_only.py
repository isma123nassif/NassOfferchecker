import json
import shutil
import subprocess
import time
from pathlib import Path


SELLER_URL = (
    "https://www.worten.pt/search?query=*&facetFilters=seller_id:"
    "e5dae97c-401c-456a-be59-56a4f73b0bb5&utm_source=sellerpage_redirect"
)
BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "fase1" / "worten_probe"
PROFILE_DIR = BASE_DIR / "fase1" / "edge_manual_worten_clean_worker"
STATE_PATH = OUT_DIR / "worker_state.json"
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        find_edge(),
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-features=msEdgeAccountExtension,msSingleSignOnOSForPrimaryAccountIsShared,EdgeSignIn,EnableSyncConsent",
        "--no-default-browser-check",
        "--no-first-run",
        "--guest",
        "--new-window",
        SELLER_URL,
    ]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    state = {
        "status": "running",
        "pid": process.pid,
        "port": PORT,
        "cdp_endpoint": f"http://127.0.0.1:{PORT}",
        "profile_dir": str(PROFILE_DIR),
        "url": SELLER_URL,
    }
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
