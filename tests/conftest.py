"""Shared pytest configuration.

``tom.config.settings`` and ``tom.api.app`` are module-level singletons, so the
first test that imports them fixes ``TOM_DATA_DIR`` for the whole session. Point
that directory at a throwaway location *before* any test module is imported so
the suite never reads or writes the developer's real ``.tom-data`` folder and
test order cannot leak credentials/memory between tests.
"""

from __future__ import annotations

import os
import tempfile

_SESSION_DATA_DIR = tempfile.mkdtemp(prefix="tom-tests-")
os.environ.setdefault("TOM_DATA_DIR", _SESSION_DATA_DIR)
os.environ.setdefault("TOM_ENV", "development")
os.environ.setdefault("TOM_LLM_ENABLED", "false")
