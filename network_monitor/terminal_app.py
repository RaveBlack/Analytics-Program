import logging
import platform
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
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
    payload_text: str
    is_plain_text: bool


class IpPrompt(ModalScreen[str]):
    """Simple modal to prompt user for an IP/host string."""

    CSS = """
    IpPrompt {
        align: center middle;
    }
    #box {
        width: 70%;
        max-width: 80;
        border: heavy $accent;
        padding: 1 2;
        background: $panel;
    }
    #actions {
        height: auto;
        padding-top: 1;
    }
    """

    def __init__(self, title: str = "Enter IP/Host", placeholder: str = "e.g. 8.8.8.8") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static(self._title)
            yield Input(placeholder=self._placeholder, id="ip_value")
            with Horizontal(id="actions"):
                yield Button("OK", id="ok", variant="primary")
                yield Button("Cancel", id="cancel", variant="error")

    def on_mount(self) -> None:
        self.query_one("#ip_value", Input).focus()

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss("")
            return
        value = (self.query_one("#ip_value", Input).value or "").strip()
        self.dismiss(value)


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
        ("t", "track_ping", "Track ping"),
        ("a", "ping_and_capture", "Ping+Capture"),
        ("s", "start_capture", "Start capture"),
        ("x", "stop_capture", "Stop capture"),
        ("z", "stop_all", "Stop all"),
        ("c", "clear_packets", "Clear table"),
    ]

    base_url: str = reactive("http://127.0.0.1:8765")
    last_packet_id: int = reactive(0)
    running: bool = reactive(False)
    filter_ip: str = reactive("")
    internet_ok: bool = reactive(False)
    tracking_ping: bool = reactive(False)

    def __init__(self, base_url: str = "http://127.0.0.1:8765") -> None:
        super().__init__()
        self.base_url = base_url
        self._session = requests.Session()
        self._packet_by_row_key: Dict[Any, Packet] = {}
        self._ping_stop = threading.Event()
        self._ping_thread: Optional[threading.Thread] = None
        self._ping_proc: Optional[subprocess.Popen[str]] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="topbar"):
            with Horizontal():
                yield Label("Target:", classes="muted")
                yield Input(placeholder="e.g. 8.8.8.8 or 192.168.1.10", id="ip")
                yield Button("Ping", id="btn_ping", variant="primary")
                yield Button("Track Ping", id="btn_track", variant="default")
                yield Button("Ping+Capture", id="btn_pingcap", variant="success")
                yield Button("Start Capture", id="btn_start", variant="success")
                yield Button("Stop", id="btn_stop", variant="warning")
                yield Button("Stop All", id="btn_stopall", variant="warning")
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
        self.set_interval(2.5, self._poll_internet)
        self._log("Ready. Tip: run as Admin (Windows) for packet capture.")

    def _start_backend_thread(self) -> None:
        # Silence werkzeug logs; they will disrupt the terminal UI.
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        host = "127.0.0.1"
        port = self._pick_backend_port(host, 8765)
        self.base_url = f"http://{host}:{port}"
        self._log(f"Backend will listen on {self.base_url}")

        def _runner() -> None:
            try:
                run_server(host=host, port=port)
            except Exception as e:
                # If backend fails to start (port in use, missing deps), surface it.
                self.call_from_thread(self._log, f"Backend failed to start: {e}")

        t = threading.Thread(target=_runner, daemon=True)
        t.start()

    def _pick_backend_port(self, host: str, preferred: int) -> int:
        # Try preferred port; if unavailable, pick an ephemeral free port.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, preferred))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, 0))
            port = s.getsockname()[1]
            s.close()
            return port

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
        self._log(
            "Backend unreachable. Common causes: port blocked/in use, antivirus/firewall, or missing dependencies. "
            "Try running `python server.py` to see the error."
        )

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
            net = "ONLINE" if self.internet_ok else "OFFLINE"
            tr = "ON" if self.tracking_ping else "OFF"
            self._set_status(
                f"Internet: {net} | TrackPing: {tr} | "
                f"Capture: {'ON' if self.running else 'OFF'} | Filter: {self.filter_ip or 'None'} | "
                f"Packets: {pkts} | Bytes: {b}"
            )
        except Exception as e:
            self._set_status(f"Backend unreachable: {e}")

    def _poll_internet(self) -> None:
        self.internet_ok = self._check_internet()

    def _check_internet(self) -> bool:
        # Quick, dependency-free connectivity check (DNS ports).
        targets = [("1.1.1.1", 53), ("8.8.8.8", 53)]
        for host, port in targets:
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    return True
            except Exception:
                continue
        return False

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
                payload_text=str(p.get("payload_text", "")),
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
        payload_text = pkt.payload_text or "[No L7 payload]"
        # Always show a plain-text L7 view (best effort / placeholder)
        view = payload_text
        if not pkt.is_plain_text and payload and payload_text != payload:
            view = view + "\n\n---\nBase64:\n" + payload
        area = self.query_one("#payload", TextArea)
        area.text = view[:20000]
        area.scroll_home(animate=False)

    def _require_target(self, title: str) -> None:
        """Prompt for target if missing; callback will continue action."""
        if self._get_ip_input():
            return
        def _set(value: str) -> None:
            if value:
                self.query_one("#ip", Input).value = value
        self.push_screen(IpPrompt(title=title), _set)

    def action_do_ping(self) -> None:
        if not self._get_ip_input():
            self._require_target("Ping target (IP/Host)")
            return
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

    def action_track_ping(self) -> None:
        if not self._get_ip_input():
            self._require_target("Track ping target (IP/Host)")
            return
        ip = self._get_ip_input()
        if not ip:
            return
        if self.tracking_ping:
            self._log("Track ping already running. Use Stop All or Stop to stop capture.")
            return
        self._start_track_ping(ip)

    def _start_track_ping(self, ip: str) -> None:
        self._ping_stop.clear()
        self.tracking_ping = True

        def worker() -> None:
            self.call_from_thread(self._log, f"Starting Track Ping -> {ip}")
            try:
                if platform.system().lower().startswith("win"):
                    cmd = ["ping", "-t", ip]
                else:
                    cmd = ["ping", ip]
                self._ping_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert self._ping_proc.stdout is not None
                for line in self._ping_proc.stdout:
                    if self._ping_stop.is_set():
                        break
                    ln = line.rstrip()
                    if ln:
                        self.call_from_thread(self._log, ln)
            except Exception as e:
                self.call_from_thread(self._log, f"Track ping error: {e}")
            finally:
                self.call_from_thread(self._stop_track_ping_internal)

        self._ping_thread = threading.Thread(target=worker, daemon=True)
        self._ping_thread.start()

    def _stop_track_ping_internal(self) -> None:
        self.tracking_ping = False
        proc = self._ping_proc
        self._ping_proc = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        self._log("Track ping stopped.")

    def action_ping_and_capture(self) -> None:
        # Prompt flow: needs target; then starts capture filtered to that target and starts track ping.
        if not self._get_ip_input():
            self._require_target("Ping+Capture target (IP/Host)")
            return
        ip = self._get_ip_input()
        if not ip:
            return
        self._log(f"Ping+Capture starting for {ip} …")
        self.action_start_capture()
        # Give capture a moment to start before ping spam
        self.call_later(lambda: self._start_track_ping(ip) if not self.tracking_ping else None)

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

    def action_stop_all(self) -> None:
        self._log("Stopping everything…")
        self._ping_stop.set()
        if self.tracking_ping:
            self._stop_track_ping_internal()
        self.action_stop_capture()

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
        elif bid == "btn_track":
            self.action_track_ping()
        elif bid == "btn_pingcap":
            self.action_ping_and_capture()
        elif bid == "btn_start":
            self.action_start_capture()
        elif bid == "btn_stop":
            self.action_stop_capture()
        elif bid == "btn_stopall":
            self.action_stop_all()
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

