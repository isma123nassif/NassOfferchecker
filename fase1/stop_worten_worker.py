import json
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = BASE_DIR / "fase1" / "worten_probe" / "worker_state.json"


def main() -> None:
    if not STATE_PATH.exists():
        print("no worker_state.json")
        return
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    pid = state.get("pid")
    if not pid:
        print("worker_state sin pid")
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    state["status"] = "stopped"
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"stopped pid {pid}")


if __name__ == "__main__":
    main()
