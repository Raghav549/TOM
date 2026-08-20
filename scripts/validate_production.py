from __future__ import annotations

import json
import os
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from tom.production import ProductionReadiness


REQUIRED_FOR_PRODUCTION = {
    "model",
    "tts",
    "asr",
    "neural_vad",
    "learned_turn",
    "vision",
    "browser",
    "device_auth",
    "persistent_data",
}


def main() -> int:
    load_dotenv()
    report = asyncio.run(ProductionReadiness().probe())
    print(json.dumps(report, indent=2, sort_keys=True))
    if os.getenv("TOM_ENV", "development").lower() != "production":
        print("TOM_ENV is not production; validation completed in advisory mode.")
        return 0
    failed = [item["name"] for item in report["checks"] if not item["configured"] and item["name"] in REQUIRED_FOR_PRODUCTION]
    if failed:
        print("Production gate failed: " + ", ".join(failed), file=sys.stderr)
        return 2
    data_dir = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
    if not data_dir.exists():
        print(f"Production gate failed: data directory does not exist: {data_dir}", file=sys.stderr)
        return 2
    print("Production capability gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
