from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from tom.android_tools import register_android_tools
from tom.api.bridge_server import install_android_bridge
from tom.api.device_ws import build_device_websocket
from tom.api.voice_ws import build_live_voice_websocket
from tom.Approval import ApprovalGate
