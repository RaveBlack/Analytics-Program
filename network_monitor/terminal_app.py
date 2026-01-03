import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TextArea,
)

from server import run_server


@dataclass
class Packet:
    id: int
    timestamp: str
    src: str
    dst: str
    protocol: str
    length: int
    summary: str
    payload: str
    is_plain_text: bool


class NetMonTUI(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #topbar {
        height: auto;
        padding: 1 1;
    }

    #statusbar {
        height: auto;
        padding: 0 1;
    }

    #main {
        height: 1fr;
        padding: 0 1;
    }

    #packets {
        height: 1fr;
    }

    #payload {
        height: 14;
        border: solid gray;
    }

    #log {
        height: 10;
        border: solid gray;
    }

    .muted {
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "do_ping", "Ping"),
        ("s", "start_capture", "Start capture"),
        ("x", "stop_capture", "Stop capture"),
        ("c", "clear_packets", "Clear table"),
    ]

    base_url: str = reactive("http://127.0.0.1:8765")
    last_packet_id: int = reactive(0)
    running: bool = reactive(False)
    filter_ip: str = reactive("")

    def __init__(self, base_url: str = "http://127.0.0.1:8765") -> None:
        super().__init__()
        self.base_url = base_url
        self._session = requests.Session()
        self._packet_by_row_key: Dict[Any, Packet] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="topbar"):
            with Horizontal():
                yield Label("Target IP:", classes="muted")
                yield Input(placeholder="e.g. 8.8.8.8 or 192.168.1.10", id="ip")
                yield Button("Ping", id="btn_ping", variant="primary")
                yield Button("Start Capture", id="btn_start", variant="success")
                yield Button("Stop", id="btn_stop", variant="warning")
                yield Button("Clear", id="btn_clear", variant="default")
                yield Button("Quit", id="btn_quit", variant="error")
        with Container(id="statusbar"):
            yield Static("", id="status")
        with Vertical(id="main"):
            table = DataTable(id="packets")
            table.cursor_type = "row"
            yield table
            yield TextArea(id="payload", read_only=True)
            yield TextArea(id="log", read_only=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#packets", DataTable)
        table.add_columns("ID", "Time", "Src", "Dst", "Proto", "Len", "Info")

        self._log("Starting local backend…")
        self._start_backend_thread()
        self._wait_for_backend()

        self.set_interval(0.75, self._poll_status)
        self.set_interval(0.35, self._poll_packets)
        self._log("Ready. Tip: run as Admin (Windows) for packet capture.")

    def _start_backend_thread(self) -> None:
        # Silence werkzeug logs; they will disrupt the terminal UI.
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        t = threading.Thread(target=run_server, kwargs={"host": "127.0.0.1", "port": 8765}, daemon=True)
        t.start()

    def _wait_for_backend(self, timeout_s: float = 4.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                r = self._session.get(f"{self.base_url}/api/health", timeout=0.4)
                if r.ok:
                    self._log("Backend is up.")
                    return
            except Exception:
                time.sleep(0.15)
        self._log("Warning: backend did not respond yet. Ping/capture may fail.")

    def _log(self, msg: str) -> None:
        area = self.query_one("#log", TextArea)
        ts = time.strftime("%H:%M:%S")
        current = area.text or ""
        new = (current + f"[{ts}] {msg}\n")[-8000:]
        area.text = new
        area.scroll_end(animate=False)

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _get_ip_input(self) -> str:
        return (self.query_one("#ip", Input).value or "").strip()

    def _safe_json(self, resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            return {"error": "Non-JSON response", "text": resp.text[:2000]}

    def _poll_status(self) -> None:
        try:
            r = self._session.get(f"{self.base_url}/api/status", timeout=0.6)
            data = self._safe_json(r)
            if not r.ok:
                self._set_status(f"Backend error: {data.get('error', r.status_code)}")
                return
            self.running = bool(data.get("running", False))
            self.filter_ip = str(data.get("filter_ip", "") or "")
            stats = data.get("stats", {}) or {}
            pkts = stats.get("packets_total", 0)
            b = stats.get("bytes_total", 0)
            self._set_status(
                f"Capture: {'ON' if self.running else 'OFF'} | Filter: {self.filter_ip or 'None'} | "
                f"Packets: {pkts} | Bytes: {b} | Backend: OK"
            )
        except Exception as e:
            self._set_status(f"Backend unreachable: {e}")

    def _poll_packets(self) -> None:
        if not self.running:
            return
        try:
            r = self._session.get(
                f"{self.base_url}/api/packets",
                params={"since": str(self.last_packet_id), "limit": "400"},
                timeout=0.8,
            )
            data = self._safe_json(r)
            if not r.ok:
                self._log(f"Packets fetch error: {data.get('error', r.status_code)}")
                return
            packets = data.get("packets", []) or []
            if packets:
                self._add_packets(packets)
        except Exception as e:
            self._log(f"Packets fetch exception: {e}")

    def _add_packets(self, packets: List[Dict[str, Any]]) -> None:
        table = self.query_one("#packets", DataTable)
        for p in packets:
            pkt = Packet(
                id=int(p.get("id", 0)),
                timestamp=str(p.get("timestamp", "")),
                src=str(p.get("src", "")),
                dst=str(p.get("dst", "")),
                protocol=str(p.get("protocol", "")),
                length=int(p.get("length", 0)),
                summary=str(p.get("summary", "")),
                payload=str(p.get("payload", "")),
                is_plain_text=bool(p.get("is_plain_text", False)),
            )
            self.last_packet_id = max(self.last_packet_id, pkt.id)
            info = pkt.summary
            if len(info) > 80:
                info = info[:80] + "…"
            row_key = table.add_row(
                str(pkt.id),
                pkt.timestamp,
                pkt.src,
                pkt.dst,
                pkt.protocol,
                str(pkt.length),
                info,
            )
            self._packet_by_row_key[row_key] = pkt

        # Keep table from growing forever
        while table.row_count > 1200:
            try:
                oldest = next(iter(table.rows))
                table.remove_row(oldest)
                self._packet_by_row_key.pop(oldest, None)
            except Exception:
                break

    @on(DataTable.RowSelected, "#packets")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        pkt = self._packet_by_row_key.get(event.row_key)
        if not pkt:
            return
        payload = pkt.payload or ""
        if not payload:
            view = "(No Layer-7 payload)"
        else:
            view = payload if pkt.is_plain_text else f"(base64) {payload}"
        area = self.query_one("#payload", TextArea)
        area.text = view[:20000]
        area.scroll_home(animate=False)

    def action_do_ping(self) -> None:
        ip = self._get_ip_input()
        if not ip:
            self._log("Enter an IP first.")
            return
        try:
            r = self._session.get(f"{self.base_url}/api/ping", params={"ip": ip, "count": "4"}, timeout=6)
            data = self._safe_json(r)
            if not r.ok:
                self._log(f"Ping failed: {data.get('error', r.status_code)}")
                return
            lines = data.get("lines", []) or []
            self._log(f"Ping {ip} -> {'OK' if data.get('ok') else 'FAIL'}")
            for ln in lines[-8:]:
                self._log(str(ln))
        except Exception as e:
            self._log(f"Ping exception: {e}")

    def action_start_capture(self) -> None:
        ip = self._get_ip_input()
        body = {"ip": ip}
        try:
            r = self._session.post(f"{self.base_url}/api/capture/start", json=body, timeout=3)
            data = self._safe_json(r)
            if not r.ok:
                self._log(f"Start capture failed: {data.get('error', r.status_code)}")
                if "text" in data:
                    self._log(data["text"])
                return
            self.running = bool(data.get("running", False))
            self.filter_ip = str(data.get("filter_ip", "") or "")
            self._log(f"Capture started. Filter: {self.filter_ip or 'None'}")
        except Exception as e:
            self._log(f"Start capture exception: {e}")

    def action_stop_capture(self) -> None:
        try:
            r = self._session.post(f"{self.base_url}/api/capture/stop", json={}, timeout=3)
            data = self._safe_json(r)
            if not r.ok:
                self._log(f"Stop capture failed: {data.get('error', r.status_code)}")
                return
            self.running = bool(data.get("running", False))
            self._log("Capture stopped.")
        except Exception as e:
            self._log(f"Stop capture exception: {e}")

    def action_clear_packets(self) -> None:
        table = self.query_one("#packets", DataTable)
        table.clear()
        self._packet_by_row_key.clear()
        self.last_packet_id = 0
        self.query_one("#payload", TextArea).text = ""
        self._log("Cleared packet table (backend buffer still exists).")

    @on(Button.Pressed)
    def _on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_ping":
            self.action_do_ping()
        elif bid == "btn_start":
            self.action_start_capture()
        elif bid == "btn_stop":
            self.action_stop_capture()
        elif bid == "btn_clear":
            self.action_clear_packets()
        elif bid == "btn_quit":
            self.exit()


if __name__ == "__main__":
    # Windows frozen apps can have odd buffering; keep output minimal.
    try:
        NetMonTUI().run()
    except KeyboardInterrupt:
        pass

