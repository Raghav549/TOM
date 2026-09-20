"""Print TOM's readiness report and gate a production deployment on it.

The required capability set comes from ``TOM_REQUIRED_CAPABILITIES`` (see
``tom.production.ProductionReadiness``) so this script, ``/ready`` and the
documentation always agree on what blocks a release.

Exit codes: ``0`` ready (or advisory mode outside production), ``2`` gate failed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from tom.production import ProductionReadiness


def main() -> int:
    load_dotenv()
    report = asyncio.run(ProductionReadiness().probe())
    print(json.dumps(report, indent=2, sort_keys=True))
    if os.getenv("TOM_ENV", "development").lower() != "production":
        print("TOM_ENV is not production; validation completed in advisory mode.")
        return 0
    failed = list(report.get("failed_required_capabilities") or [])
    if failed:
        print("Production gate failed: " + ", ".join(failed), file=sys.stderr)
        return 2
    data_dir = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
    if not data_dir.exists():
        print(f"Production gate failed: data directory does not exist: {data_dir}", file=sys.stderr)
        return 2
    degraded = list(report.get("degraded_capabilities") or [])
    if degraded:
        print("Optional capabilities degraded (not blocking): " + ", ".join(degraded))
    print("Production capability gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
