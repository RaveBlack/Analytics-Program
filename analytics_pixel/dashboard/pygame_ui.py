from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pygame
import pyperclip
import requests

from .charts import draw_line_chart
from .theme import Theme


@dataclass
class ServerState:
    base_url: str = "http://127.0.0.1:5055"
    token: Optional[str] = None
    username: str = "admin"
    password: str = ""
    message: str = ""
    last_refresh: float = 0.0


def _text(font: pygame.font.Font, s: str, color=Theme.TEXT) -> pygame.Surface:
    return font.render(s, True, color)


def _clip_copy(s: str) -> None:
    # pyperclip gives reliable copy/paste on Linux compared to pygame.scrap
    pyperclip.copy(s)


def _auth_headers(state: ServerState) -> Dict[str, str]:
    if not state.token:
        return {}
    return {"Authorization": f"Bearer {state.token}"}


def _api_post(state: ServerState, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = state.base_url.rstrip("/") + path
    r = requests.post(url, json=payload, headers=_auth_headers(state), timeout=5)
    return {"status": r.status_code, "json": (r.json() if r.content else {})}


def _api_get(state: ServerState, path: str) -> Dict[str, Any]:
    url = state.base_url.rstrip("/") + path
    r = requests.get(url, headers=_auth_headers(state), timeout=5)
    return {"status": r.status_code, "json": (r.json() if r.content else {})}


class InputBox:
    def __init__(self, rect: pygame.Rect, *, text: str = "", password: bool = False):
        self.rect = rect
        self.text = text
        self.active = False
        self.password = password

    def handle_event(self, e: pygame.event.Event) -> None:
        if e.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(e.pos)
        if e.type == pygame.KEYDOWN and self.active:
            if e.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif e.key == pygame.K_RETURN:
                pass
            elif e.key == pygame.K_v and (e.mod & pygame.KMOD_CTRL):
                try:
                    self.text += pyperclip.paste()
                except Exception:
                    pass
            else:
                if e.unicode and len(e.unicode) == 1:
                    self.text += e.unicode

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, label: str) -> None:
        pygame.draw.rect(surf, Theme.PANEL_2, self.rect, border_radius=8)
        pygame.draw.rect(surf, Theme.BORDER, self.rect, width=1, border_radius=8)
        surf.blit(_text(font, label, Theme.MUTED), (self.rect.x, self.rect.y - 18))
        shown = ("•" * len(self.text)) if self.password else self.text
        surf.blit(_text(font, shown), (self.rect.x + 10, self.rect.y + 8))


class Button:
    def __init__(self, rect: pygame.Rect, text: str):
        self.rect = rect
        self.text = text
        self.hover = False

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(e.pos)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            return self.rect.collidepoint(e.pos)
        return False

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        color = (40, 45, 55) if not self.hover else (55, 62, 75)
        pygame.draw.rect(surf, color, self.rect, border_radius=10)
        pygame.draw.rect(surf, Theme.BORDER, self.rect, width=1, border_radius=10)
        txt = _text(font, self.text)
        surf.blit(txt, (self.rect.centerx - txt.get_width() // 2, self.rect.centery - txt.get_height() // 2))


def run_dashboard() -> None:
    pygame.init()
    pygame.display.set_caption("Analytics Pixel Dashboard (Local)")

    screen = pygame.display.set_mode((1200, 720))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 18)
    font_small = pygame.font.SysFont("Segoe UI", 14)
    font_big = pygame.font.SysFont("Segoe UI", 28, bold=True)

    state = ServerState()

    # Inputs
    inp_url = InputBox(pygame.Rect(30, 60, 420, 36), text=state.base_url)
    inp_user = InputBox(pygame.Rect(470, 60, 160, 36), text=state.username)
    inp_pass = InputBox(pygame.Rect(650, 60, 200, 36), text=state.password, password=True)

    inp_new_pixel = InputBox(pygame.Rect(30, 160, 220, 36), text="pixel_001")
    inp_new_label = InputBox(pygame.Rect(270, 160, 260, 36), text="homepage")

    btn_login = Button(pygame.Rect(870, 60, 130, 36), "Login")
    btn_setup = Button(pygame.Rect(1010, 60, 160, 36), "First-time Setup")
    btn_refresh = Button(pygame.Rect(1030, 160, 140, 36), "Refresh")
    btn_create = Button(pygame.Rect(550, 160, 160, 36), "Create Pixel")

    # Data
    summary: Dict[str, Any] = {"total_hits": 0, "unique_visitors": 0, "pixel_count": 0}
    pixels: List[Dict[str, Any]] = []
    series: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    selected_pixel_id: Optional[str] = None
    selected_embed: Optional[Dict[str, str]] = None

    scroll = 0

    def refresh() -> None:
        nonlocal summary, pixels, series, events, selected_embed
        if not state.token:
            return
        try:
            s = _api_get(state, "/api/stats/summary")
            p = _api_get(state, "/api/stats/pixels")
            t = _api_get(state, "/api/stats/timeseries?bucket=hour&hours=48")
            e = _api_get(state, "/api/events/recent?limit=30")
            if s["status"] == 200:
                summary = s["json"]
            if p["status"] == 200:
                pixels = p["json"].get("pixels", [])
            if t["status"] == 200:
                series = t["json"].get("series", [])
            if e["status"] == 200:
                events = e["json"].get("events", [])
            state.last_refresh = time.time()
            state.message = "Refreshed."
            # keep embed info if selection still exists
            if selected_pixel_id:
                selected_embed = _make_embed(selected_pixel_id)
        except Exception as e:
            state.message = f"Refresh failed: {e}"

    def _make_embed(pixel_id: str) -> Dict[str, str]:
        base = state.base_url.rstrip("/")
        return {
            "bbcode": f"[img]{base}/p/{pixel_id}.png[/img]",
            "bbcode_with_tag": f"[img]{base}/p/{pixel_id}.png?tag=campaign[/img]",
            "bbcode_glyph": f"[img]{base}/g/{pixel_id}.png?text=%E2%80%A2[/img]",
            "pixel_url": f"{base}/p/{pixel_id}.png",
        }

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False

            for inp in (inp_url, inp_user, inp_pass, inp_new_pixel, inp_new_label):
                inp.handle_event(e)

            if e.type == pygame.MOUSEWHEEL:
                scroll = max(0, scroll - e.y * 24)

            if btn_login.handle_event(e):
                state.base_url = inp_url.text.strip()
                state.username = inp_user.text.strip()
                state.password = inp_pass.text
                try:
                    res = _api_post(state, "/api/login", {"username": state.username, "password": state.password})
                    if res["status"] == 200 and res["json"].get("token"):
                        state.token = res["json"]["token"]
                        state.message = "Logged in."
                        refresh()
                    else:
                        state.message = f"Login failed: {res['json'].get('error','unknown')}"
                except Exception as ex:
                    state.message = f"Login error: {ex}"

            if btn_setup.handle_event(e):
                state.base_url = inp_url.text.strip()
                state.username = inp_user.text.strip()
                state.password = inp_pass.text
                try:
                    res = _api_post(state, "/api/setup", {"username": state.username, "password": state.password})
                    if res["status"] == 200 and res["json"].get("token"):
                        state.token = res["json"]["token"]
                        state.message = "Setup complete (admin created)."
                        refresh()
                    else:
                        state.message = f"Setup failed: {res['json'].get('error','unknown')}"
                except Exception as ex:
                    state.message = f"Setup error: {ex}"

            if btn_refresh.handle_event(e):
                refresh()

            if btn_create.handle_event(e):
                if not state.token:
                    state.message = "Login first."
                else:
                    pixel_id = inp_new_pixel.text.strip()
                    label = inp_new_label.text.strip()
                    try:
                        res = _api_post(state, "/api/pixels/create", {"pixel_id": pixel_id, "label": label})
                        if res["status"] == 200 and res["json"].get("embed"):
                            selected_pixel_id = pixel_id
                            selected_embed = res["json"]["embed"]
                            state.message = f"Created pixel: {pixel_id}"
                            refresh()
                        else:
                            state.message = f"Create failed: {res['json'].get('error','unknown')}"
                    except Exception as ex:
                        state.message = f"Create error: {ex}"

            # Click selection + copy actions in table
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                mx, my = e.pos
                table_rect = pygame.Rect(30, 240, 560, 450)
                if table_rect.collidepoint(mx, my):
                    row_h = 30
                    idx = (my - table_rect.y + scroll) // row_h - 1  # header row
                    if 0 <= idx < len(pixels):
                        selected_pixel_id = str(pixels[idx].get("pixel_id"))
                        selected_embed = _make_embed(selected_pixel_id)
                        state.message = f"Selected: {selected_pixel_id} (click copy buttons on right)"

                # Copy buttons
                if selected_embed:
                    y0 = 300
                    copy_rects = [
                        ("BBCode", pygame.Rect(650, y0, 220, 34), selected_embed["bbcode"]),
                        ("BBCode+tag", pygame.Rect(650, y0 + 44, 220, 34), selected_embed["bbcode_with_tag"]),
                        ("Glyph BBCode", pygame.Rect(650, y0 + 88, 220, 34), selected_embed["bbcode_glyph"]),
                        ("Pixel URL", pygame.Rect(650, y0 + 132, 220, 34), selected_embed["pixel_url"]),
                    ]
                    for label, rect, val in copy_rects:
                        if rect.collidepoint(mx, my):
                            try:
                                _clip_copy(val)
                                state.message = f"Copied {label} to clipboard."
                            except Exception as ex:
                                state.message = f"Copy failed: {ex}"

        # Auto-poll (simple)
        refresh_every = 2.0
        if state.token and time.time() - state.last_refresh > refresh_every:
            refresh()

        # ---- draw ----
        screen.fill(Theme.BG)

        # Title bar
        screen.blit(_text(font_big, "Analytics Pixel (privacy-first, local)"), (30, 20))
        screen.blit(_text(font_small, "Identifiable mode may store/display raw IP/UA/Referrer (see config.yaml).", Theme.MUTED), (30, 110))

        # Login row
        inp_url.draw(screen, font, "Server URL")
        inp_user.draw(screen, font, "Username")
        inp_pass.draw(screen, font, "Password")
        btn_login.draw(screen, font)
        btn_setup.draw(screen, font_small)

        # Message
        if state.message:
            screen.blit(_text(font_small, state.message, Theme.MUTED), (30, 700))

        # Summary cards
        def card(x: int, y: int, w: int, h: int, title: str, value: str) -> None:
            r = pygame.Rect(x, y, w, h)
            pygame.draw.rect(screen, Theme.PANEL, r, border_radius=12)
            pygame.draw.rect(screen, Theme.BORDER, r, width=1, border_radius=12)
            screen.blit(_text(font_small, title, Theme.MUTED), (x + 14, y + 10))
            screen.blit(_text(font_big, value, Theme.TEXT), (x + 14, y + 32))

        card(30, 130, 180, 90, "Total hits", str(summary.get("total_hits", 0)))
        card(220, 130, 220, 90, "Unique visitors (hashed)", str(summary.get("unique_visitors", 0)))
        card(450, 130, 180, 90, "Pixels", str(summary.get("pixel_count", 0)))

        # Create pixel row
        inp_new_pixel.draw(screen, font, "New Pixel ID")
        inp_new_label.draw(screen, font, "Label (optional)")
        btn_create.draw(screen, font)
        btn_refresh.draw(screen, font)

        # Pixels table
        table = pygame.Rect(30, 240, 560, 450)
        pygame.draw.rect(screen, Theme.PANEL, table, border_radius=12)
        pygame.draw.rect(screen, Theme.BORDER, table, width=1, border_radius=12)

        header = ["Pixel ID", "Label", "Hits", "Unique"]
        col_x = [table.x + 14, table.x + 210, table.x + 400, table.x + 480]
        screen.blit(_text(font_small, header[0], Theme.MUTED), (col_x[0], table.y + 10))
        screen.blit(_text(font_small, header[1], Theme.MUTED), (col_x[1], table.y + 10))
        screen.blit(_text(font_small, header[2], Theme.MUTED), (col_x[2], table.y + 10))
        screen.blit(_text(font_small, header[3], Theme.MUTED), (col_x[3], table.y + 10))
        pygame.draw.line(screen, Theme.BORDER, (table.x + 10, table.y + 34), (table.x + table.w - 10, table.y + 34), 1)

        # Scrollable content
        content_top = table.y + 40
        row_h = 30
        clip = screen.get_clip()
        screen.set_clip(table.inflate(-10, -50))
        for i, row in enumerate(pixels):
            y = content_top + i * row_h - scroll
            rid = str(row.get("pixel_id", ""))
            if y + row_h < table.y + 40 or y > table.y + table.h - 10:
                continue
            is_sel = (selected_pixel_id == rid)
            if is_sel:
                pygame.draw.rect(screen, (40, 55, 75), pygame.Rect(table.x + 8, y, table.w - 16, row_h), border_radius=8)
            screen.blit(_text(font_small, rid, Theme.TEXT), (col_x[0], y + 6))
            screen.blit(_text(font_small, str(row.get("label", ""))[:20], Theme.MUTED), (col_x[1], y + 6))
            screen.blit(_text(font_small, str(row.get("hits", 0)), Theme.TEXT), (col_x[2], y + 6))
            screen.blit(_text(font_small, str(row.get("unique_visitors", 0)), Theme.TEXT), (col_x[3], y + 6))
        screen.set_clip(clip)

        # Chart
        chart_rect = pygame.Rect(610, 240, 560, 180)
        # Scale series into points
        hits_vals = [int(p.get("hits", 0)) for p in series] if series else []
        maxv = max(hits_vals) if hits_vals else 1
        pts: List[Tuple[int, int]] = []
        if series:
            for i, p in enumerate(series):
                x = chart_rect.x + 20 + int((chart_rect.w - 40) * (i / max(1, len(series) - 1)))
                y = chart_rect.y + chart_rect.h - 20 - int((chart_rect.h - 40) * (int(p.get("hits", 0)) / maxv))
                pts.append((x, y))
        draw_line_chart(screen, chart_rect, points=pts, color=Theme.ACCENT)
        screen.blit(_text(font_small, "Hits (last 48 hours, hourly buckets)", Theme.MUTED), (chart_rect.x + 14, chart_rect.y + 10))

        # Embed/copy panel
        panel = pygame.Rect(610, 440, 560, 250)
        pygame.draw.rect(screen, Theme.PANEL, panel, border_radius=12)
        pygame.draw.rect(screen, Theme.BORDER, panel, width=1, border_radius=12)
        screen.blit(_text(font, "Embed / Copy", Theme.TEXT), (panel.x + 14, panel.y + 12))
        if not selected_pixel_id:
            screen.blit(_text(font_small, "Select a pixel from the table to copy embed codes.", Theme.MUTED), (panel.x + 14, panel.y + 44))
        else:
            screen.blit(_text(font_small, f"Selected: {selected_pixel_id}", Theme.MUTED), (panel.x + 14, panel.y + 44))

            # Copy buttons
            y0 = 300
            btns = [
                ("BBCode", "[img].../p/<id>.png[/img]"),
                ("BBCode+tag", "[img].../p/<id>.png?tag=campaign[/img]"),
                ("Glyph BBCode", "[img].../g/<id>.png?text=•[/img]"),
                ("Pixel URL", ".../p/<id>.png"),
            ]
            rects = [
                pygame.Rect(650, y0, 220, 34),
                pygame.Rect(650, y0 + 44, 220, 34),
                pygame.Rect(650, y0 + 88, 220, 34),
                pygame.Rect(650, y0 + 132, 220, 34),
            ]
            for (label, hint), r in zip(btns, rects):
                pygame.draw.rect(screen, (40, 45, 55), r, border_radius=10)
                pygame.draw.rect(screen, Theme.BORDER, r, width=1, border_radius=10)
                screen.blit(_text(font_small, f"Copy {label}", Theme.TEXT), (r.x + 12, r.y + 8))
                screen.blit(_text(font_small, hint, Theme.MUTED), (r.x + 240, r.y + 8))

        # Recent hits (shows identifiable data if stored)
        recent = pygame.Rect(610, 430, 560, 0)  # just a label line above panel
        screen.blit(_text(font, "Recent hits (raw if available)", Theme.TEXT), (610 + 14, 420))
        y = 448
        for ev in events[:6]:
            pid = str(ev.get("pixel_id", ""))
            ip = ev.get("ip_raw") or (str(ev.get("ip_hash", ""))[:10] + "…")
            ua = ev.get("ua_raw") or (str(ev.get("ua_hash", ""))[:10] + "…")
            ref = ev.get("ref_raw") or (str(ev.get("ref_hash", ""))[:10] + "…")
            line = f"{pid}  IP={ip}  UA={str(ua)[:28]}  REF={str(ref)[:28]}"
            screen.blit(_text(font_small, line, Theme.MUTED), (610 + 14, y))
            y += 16

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    run_dashboard()

