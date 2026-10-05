"""Opt-in, read-only document tools confined to an operator-selected directory.

This is not an OS sandbox: do not share the root with an untrusted writer capable
of swapping paths while they are read. Hidden files and symlinks are not exposed.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Risk
from .tools import ToolRegistry


@dataclass
class WorkspaceTool:
    root: Path
    name: str
    description: str
    risk: Risk = Risk.READ

    def _path(self, value: str) -> Path:
        relative = Path(value)
        if relative.is_absolute() or any(part == ".." or part.startswith(".") for part in relative.parts):
            raise PermissionError("Only non-hidden workspace-relative paths are allowed")
        path = self.root
        for part in relative.parts:
            path /= part
            if path.is_symlink():
                raise PermissionError("Workspace symlinks are not exposed")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.root):
            raise PermissionError("Path escapes the configured workspace")
        return resolved

    def _run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._path(str(arguments.get("path", "")))
        if self.name == "filesystem.list":
            entries = []
            for child in path.iterdir():
                if child.name.startswith(".") or child.is_symlink():
                    continue
                entries.append({"name": child.name, "directory": child.is_dir()})
                if len(entries) > 500:
                    raise ValueError("Directory exceeds 500 entries; choose a narrower path")
            return {"ok": True, "entries": sorted(entries, key=lambda x: x["name"])}
        if not path.is_file():
            raise ValueError("Path must be a regular UTF-8 text file")
        with path.open("rb") as handle:
            data = handle.read(262145)
        if len(data) > 262144:
            raise ValueError("File exceeds the 256 KiB reading limit")
        return {"ok": True, "path": str(path.relative_to(self.root)), "content": data.decode("utf-8"),
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._run, arguments)


def register_workspace_tools(registry: ToolRegistry) -> None:
    configured = os.getenv("TOM_WORKSPACE_DIR", "").strip()
    if not configured:
        return
    root = Path(configured).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("TOM_WORKSPACE_DIR must be a directory")
    registry.register(WorkspaceTool(root, "filesystem.list", "List non-hidden entries. arguments: {path: relative directory, default empty for root}."))
    registry.register(WorkspaceTool(root, "filesystem.read", "Read a UTF-8 document up to 256 KiB with SHA-256 receipt. arguments: {path: relative file path}."))
