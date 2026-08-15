"""Async Moonraker client: JSON-RPC over websocket plus REST helpers."""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any, Callable

import httpx
import websockets

# Printer objects we subscribe to. None = all fields of that object.
SUBSCRIPTIONS: dict[str, list[str] | None] = {
    "webhooks": None,
    "print_stats": None,
    "display_status": None,
    "virtual_sdcard": None,
    "toolhead": None,
    "gcode_move": None,
    "extruder": None,
    "heater_bed": None,
    "fan": None,
    "idle_timeout": None,
    "bed_mesh": None,
    "motion_report": None,
    "firmware_retraction": None,
    "configfile": ["config", "settings"],
}


class MoonrakerError(Exception):
    """Raised when Moonraker returns a JSON-RPC error response."""


class MoonrakerClient:
    """Maintains a websocket to Moonraker, exposing live state and commands.

    Callers register callbacks for status updates, gcode responses, and
    connectivity changes; the client reconnects on its own if the socket drops.
    """

    def __init__(self, host: str, port: int = 7125) -> None:
        self.host = host
        self.port = port
        self.status: dict[str, dict[str, Any]] = {}
        self.connected = False
        self.klippy_state = "unknown"

        self._ws: Any = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._on_status: list[Callable[[dict], None]] = []
        self._on_gcode: list[Callable[[str], None]] = []
        self._on_conn: list[Callable[[bool, str], None]] = []

    @property
    def http_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/websocket"

    # -- callback registration -------------------------------------------------

    def on_status(self, fn: Callable[[dict], None]) -> None:
        self._on_status.append(fn)

    def on_gcode_response(self, fn: Callable[[str], None]) -> None:
        self._on_gcode.append(fn)

    def on_connection_change(self, fn: Callable[[bool, str], None]) -> None:
        self._on_conn.append(fn)

    # -- connection lifecycle --------------------------------------------------

    async def run(self) -> None:
        """Connect and pump messages forever, reconnecting on failure."""
        while True:
            handshake: asyncio.Task | None = None
            try:
                async with websockets.connect(self.ws_url, max_size=None) as ws:
                    self._ws = ws
                    self.connected = True
                    self._emit_conn()
                    # The handshake awaits RPC replies, which only arrive once
                    # the read loop below is pumping, so it must run alongside.
                    handshake = asyncio.create_task(self._handshake())
                    async for raw in ws:
                        self._dispatch(json.loads(raw))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                if handshake and not handshake.done():
                    handshake.cancel()
                self._ws = None
                self.connected = False
                self._fail_pending()
                self._emit_conn()
            await asyncio.sleep(2)

    async def _handshake(self) -> None:
        try:
            info = await self.call("server.info")
            self.klippy_state = info.get("klippy_state", "unknown")
            self._emit_conn()
            if self.klippy_state == "ready":
                await self._resubscribe()
        except (MoonrakerError, asyncio.CancelledError):
            pass

    def _fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MoonrakerError("connection lost"))
        self._pending.clear()

    # -- message dispatch ------------------------------------------------------

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg:
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(
                        MoonrakerError(msg["error"].get("message", "unknown error"))
                    )
                else:
                    fut.set_result(msg.get("result", {}))
            return

        method = msg.get("method")
        params = msg.get("params", [])

        if method == "notify_status_update" and params:
            self._merge(params[0])
            self._emit_status()
        elif method == "notify_gcode_response" and params:
            for fn in self._on_gcode:
                fn(params[0])
        elif method in ("notify_klippy_ready", "notify_klippy_shutdown",
                        "notify_klippy_disconnected"):
            self.klippy_state = method.replace("notify_klippy_", "")
            if method == "notify_klippy_ready":
                asyncio.create_task(self._resubscribe())
            self._emit_conn()

    async def _resubscribe(self) -> None:
        try:
            result = await self.call(
                "printer.objects.subscribe", {"objects": SUBSCRIPTIONS}
            )
            self._merge(result.get("status", {}))
            self._emit_status()
        except MoonrakerError:
            pass

    def _merge(self, update: dict) -> None:
        for obj, fields in update.items():
            self.status.setdefault(obj, {}).update(fields)

    def _emit_status(self) -> None:
        for fn in self._on_status:
            fn(self.status)

    def _emit_conn(self) -> None:
        for fn in self._on_conn:
            fn(self.connected, self.klippy_state)

    # -- JSON-RPC --------------------------------------------------------------

    async def call(self, method: str, params: dict | None = None,
                   timeout: float = 15.0) -> dict:
        if self._ws is None:
            raise MoonrakerError("not connected")
        req_id = next(self._ids)
        payload = {"jsonrpc": "2.0", "method": method, "id": req_id}
        if params:
            payload["params"] = params
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        await self._ws.send(json.dumps(payload))
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise MoonrakerError(f"{method} timed out")

    # -- commands --------------------------------------------------------------

    async def gcode(self, script: str) -> dict:
        return await self.call("printer.gcode.script", {"script": script})

    async def emergency_stop(self) -> dict:
        return await self.call("printer.emergency_stop")

    async def firmware_restart(self) -> dict:
        return await self.call("printer.firmware_restart")

    async def restart(self) -> dict:
        return await self.call("printer.restart")

    async def print_start(self, filename: str) -> dict:
        return await self.call("printer.print.start", {"filename": filename})

    async def print_pause(self) -> dict:
        return await self.call("printer.print.pause")

    async def print_resume(self) -> dict:
        return await self.call("printer.print.resume")

    async def print_cancel(self) -> dict:
        return await self.call("printer.print.cancel")

    async def list_gcode_files(self) -> list[dict]:
        result = await self.call("server.files.list", {"root": "gcodes"})
        return result if isinstance(result, list) else result.get("files", [])

    async def fetch_json(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.http_url}{path}")
            resp.raise_for_status()
            return resp.json().get("result", {})
