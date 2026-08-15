from __future__ import annotations

"""Validate/summarize TOM's curated Public APIs catalogue.

The upstream repository is intentionally not copied wholesale into the runtime:
it is a discovery catalogue and entries change. Run this script during a
maintenance/update cycle to compare TOM's typed adapters with the upstream list.
"""

import re
import urllib.request
from collections import Counter

UPSTREAM = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"


def main() -> None:
    with urllib.request.urlopen(UPSTREAM, timeout=20) as response:  # noqa: S310 - fixed HTTPS source
        text = response.read().decode("utf-8")
    headings = re.findall(r"^### (.+)$", text, re.MULTILINE)
    rows = re.findall(r"^\| \[([^\]]+)\]\(([^)]+)\) \| ([^|]+) \| `?([^|`]*)`? \|", text, re.MULTILINE)
    print(f"upstream_categories={len(headings)}")
    print(f"upstream_entries={len(rows)}")
    print("top_categories:")
    for category, count in Counter(headings).most_common(20):
        print(f"  {category}: {count}")
    print("note=upstream entries require individual adapter validation before execution")


if __name__ == "__main__":
    main()
