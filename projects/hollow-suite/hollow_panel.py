#!/usr/bin/env python3
"""
hollow-panel: Sleek Hollow Purple Glassmorphism Popup combining:
  - Quick Dev Service Panel (PostgreSQL, MySQL, Mode Fokus / Hemat Baterai, Visualizer, Active Ports)
  - Searchable Clipboard History Manager (Super+V)
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

DATA_DIR = Path.home() / ".local" / "share" / "hollow-suite"
CLIP_FILE = DATA_DIR / "clipboard.json"
FOCUS_FLAG = Path.home() / ".config" / "hollow-suite" / "focus-mode"

LAYER_OVERLAY = 3
KB_EXCLUSIVE = 1

HEAVY_USER_SERVICES = [
    "gojo-live-wallpaper.service",
    "cosmic-live-particles.service",
    "hollow-visualizer.service",
]

CSS_THEME = b"""
window {
    background-color: rgba(13, 14, 24, 0.92);
    border: 1px solid rgba(192, 132, 252, 0.48);
    border-radius: 16px;
    color: #eef2ff;
}
.title-lbl {
    font-size: 16px;
    font-weight: 700;
    color: #f5f3ff;
}
.sub-lbl {
    font-size: 12px;
    color: #94a3b8;
}
.tab-btn {
    background: rgba(30, 32, 54, 0.85);
    color: #cbd5e1;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 9px;
    padding: 6px 14px;
    font-weight: 600;
}
.tab-btn.active {
    background: rgba(139, 92, 246, 0.35);
    color: #f5f3ff;
    border-color: rgba(192, 132, 252, 0.75);
}
.card-btn {
    background: rgba(24, 26, 44, 0.85);
    color: #e2e8f0;
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 11px;
    padding: 10px 12px;
}
.card-btn:hover {
    background: rgba(139, 92, 246, 0.20);
    border-color: rgba(192, 132, 252, 0.60);
}
.card-btn.running {
    background: rgba(16, 185, 129, 0.14);
    border-color: rgba(52, 211, 153, 0.55);
}
.section-hdr {
    font-size: 12px;
    font-weight: 700;
    color: #c084fc;
}
.port-box, .clip-list {
    background: rgba(18, 20, 34, 0.78);
    border: 1px solid rgba(148, 163, 184, 0.20);
    border-radius: 10px;
    padding: 6px;
}
.clip-row {
    background: rgba(30, 33, 56, 0.55);
    color: #e2e8f0;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 8px;
    padding: 7px 10px;
    margin-bottom: 4px;
}
.clip-row:hover {
    background: rgba(139, 92, 246, 0.28);
    border-color: rgba(192, 132, 252, 0.65);
}
entry {
    background: rgba(20, 22, 38, 0.95);
    color: #f8fafc;
    border: 1px solid rgba(167, 139, 250, 0.45);
    border-radius: 9px;
    padding: 6px 10px;
}
.action-btn {
    background: rgba(56, 189, 248, 0.16);
    color: #e0f2fe;
    border: 1px solid rgba(56, 189, 248, 0.42);
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
}
.action-btn:hover {
    background: rgba(56, 189, 248, 0.28);
}
.close-btn {
    background: rgba(248, 113, 113, 0.14);
    color: #fecaca;
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 8px;
    padding: 4px 10px;
}
"""


class _PyGObjectStruct(ctypes.Structure):
    _fields_ = [("ob_refcnt", ctypes.c_ssize_t), ("ob_type", ctypes.c_void_p), ("obj", ctypes.c_void_p)]


def _gobject_ptr(obj: object) -> int:
    return _PyGObjectStruct.from_address(id(obj)).obj


def _setup_layer_shell(win: Gtk.Window) -> None:
    try:
        lib = ctypes.CDLL("libgtk-layer-shell.so.0")
        lib.gtk_layer_is_supported.restype = ctypes.c_bool
        if not lib.gtk_layer_is_supported():
            return
        lib.gtk_layer_init_for_window.argtypes = [ctypes.c_void_p]
        lib.gtk_layer_set_layer.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_keyboard_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_namespace.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        ptr = _gobject_ptr(win)
        lib.gtk_layer_init_for_window(ptr)
        lib.gtk_layer_set_namespace(ptr, b"hollow-dev-panel")
        lib.gtk_layer_set_layer(ptr, LAYER_OVERLAY)
        lib.gtk_layer_set_keyboard_mode(ptr, KB_EXCLUSIVE)
    except OSError:
        pass


def is_sys_service_active(name: str, user: bool = False) -> bool:
    cmd = ["systemctl", "--user", "is-active", "--quiet", name] if user else ["systemctl", "is-active", "--quiet", name]
    return subprocess.run(cmd, check=False).returncode == 0


def get_listening_ports() -> List[Tuple[str, str]]:
    ports: List[Tuple[str, str]] = []
    try:
        out = subprocess.check_output(["ss", "-tlnp"], text=True, stderr=subprocess.DEVNULL)
        seen = set()
        for line in out.splitlines()[1:]:
            cols = line.split()
            if len(cols) < 4:
                continue
            local = cols[3]
            port = local.rsplit(":", 1)[-1]
            if not port.isdigit() or port in seen:
                continue
            seen.add(port)
            proc = ""
            m = re.search(r'"([^"]+)"', line)
            if m:
                proc = m.group(1)
            ports.append((port, proc or "service"))
    except Exception:
        pass
    return sorted(ports, key=lambda x: int(x[0]))[:10]


def load_clipboard_items() -> List[dict]:
    if CLIP_FILE.exists():
        try:
            d = json.loads(CLIP_FILE.read_text(encoding="utf-8"))
            if isinstance(d, list):
                return d
        except (OSError, json.JSONDecodeError):
            pass
    return []


class HollowPanelWindow(Gtk.Window):
    def __init__(self, initial_tab: str = "dev") -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_default_size(640, 440)
        self.set_position(Gtk.WindowPosition.CENTER)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        css = Gtk.CssProvider()
        css.load_from_data(CSS_THEME)
        Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        _setup_layer_shell(self)

        self.connect("key-press-event", self.on_key)
        self.connect("destroy", Gtk.main_quit)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(18)
        root.set_margin_end(18)
        self.add(root)

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl = Gtk.Label(label="Hollow Suite Panel")
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("title-lbl")
        sub = Gtk.Label(label="Pop!_OS COSMIC · Tekan Esc untuk tutup")
        sub.set_halign(Gtk.Align.START)
        sub.get_style_context().add_class("sub-lbl")
        title_box.pack_start(lbl, False, False, 0)
        title_box.pack_start(sub, False, False, 0)
        hdr.pack_start(title_box, True, True, 0)

        self.btn_tab_dev = Gtk.Button(label="Dev Panel")
        self.btn_tab_dev.get_style_context().add_class("tab-btn")
        self.btn_tab_dev.connect("clicked", lambda _b: self.switch_tab("dev"))

        self.btn_tab_clip = Gtk.Button(label="Clipboard (Super+V)")
        self.btn_tab_clip.get_style_context().add_class("tab-btn")
        self.btn_tab_clip.connect("clicked", lambda _b: self.switch_tab("clip"))

        btn_close = Gtk.Button(label="✕")
        btn_close.get_style_context().add_class("close-btn")
        btn_close.connect("clicked", lambda _b: self.destroy())

        hdr.pack_end(btn_close, False, False, 0)
        hdr.pack_end(self.btn_tab_clip, False, False, 0)
        hdr.pack_end(self.btn_tab_dev, False, False, 0)
        root.pack_start(hdr, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        root.pack_start(self.stack, True, True, 0)

        self._build_dev_tab()
        self._build_clip_tab()

        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.set_halign(Gtk.Align.START)
        self.status_lbl.get_style_context().add_class("sub-lbl")
        root.pack_start(self.status_lbl, False, False, 0)

        self.show_all()
        self.switch_tab(initial_tab)

    def on_key(self, _w: Gtk.Widget, ev: Gdk.EventKey) -> bool:
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def switch_tab(self, name: str) -> None:
        self.stack.set_visible_child_name(name)
        for btn, key in ((self.btn_tab_dev, "dev"), (self.btn_tab_clip, "clip")):
            ctx = btn.get_style_context()
            if key == name:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")
        if name == "clip":
            self._refresh_clipboard()
            self.clip_search.grab_focus()
        else:
            self._refresh_dev()

    def _build_dev_tab(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        sec1 = Gtk.Label(label="Layanan & Mode Cepat (Klik untuk Toggle)")
        sec1.set_halign(Gtk.Align.START)
        sec1.get_style_context().add_class("section-hdr")
        box.pack_start(sec1, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        self.svc_cards = {}
        defs = [
            ("postgresql", "PostgreSQL", 0, 0),
            ("mysql", "MySQL", 1, 0),
            ("focus", "Mode Fokus / Hemat", 0, 1),
            ("viz", "Audio Visualizer", 1, 1),
        ]
        for key, title, col, row in defs:
            btn = Gtk.Button()
            btn.get_style_context().add_class("card-btn")
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            t_lbl = Gtk.Label(label=title)
            t_lbl.set_halign(Gtk.Align.START)
            s_lbl = Gtk.Label(label="Memeriksa...")
            s_lbl.set_halign(Gtk.Align.START)
            s_lbl.get_style_context().add_class("sub-lbl")
            vbox.pack_start(t_lbl, False, False, 0)
            vbox.pack_start(s_lbl, False, False, 0)
            btn.add(vbox)
            btn.connect("clicked", lambda _b, k=key: self._toggle_service(k))
            grid.attach(btn, col, row, 1, 1)
            self.svc_cards[key] = (btn, s_lbl)
        box.pack_start(grid, False, False, 0)

        # Active local listening ports
        sec2 = Gtk.Label(label="Port Lokal Aktif (ss -tlnp)")
        sec2.set_halign(Gtk.Align.START)
        sec2.get_style_context().add_class("section-hdr")
        box.pack_start(sec2, False, False, 0)

        self.ports_lbl = Gtk.Label(label="Memuat port...")
        self.ports_lbl.set_halign(Gtk.Align.START)
        self.ports_lbl.set_valign(Gtk.Align.START)
        self.ports_lbl.set_line_wrap(True)
        pwrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pwrap.get_style_context().add_class("port-box")
        pwrap.pack_start(self.ports_lbl, True, True, 4)
        box.pack_start(pwrap, True, True, 0)

        # Quick launch row
        qrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, cmd in (
            ("Buka btop (Monitor)", ["cosmic-term", "-e", "/home/kerja/.local/bin/btop"]),
            ("Buka lazygit", ["cosmic-term", "-e", "/home/kerja/.local/bin/lazygit"]),
            ("Refresh", None),
        ):
            b = Gtk.Button(label=label)
            b.get_style_context().add_class("action-btn")
            if cmd is None:
                b.connect("clicked", lambda _w: self._refresh_dev())
            else:
                b.connect("clicked", lambda _w, c=cmd: self._launch_and_close(c))
            qrow.pack_start(b, False, False, 0)
        box.pack_end(qrow, False, False, 0)

        self.stack.add_named(box, "dev")

    def _launch_and_close(self, cmd: List[str]) -> None:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.destroy()

    def _refresh_dev(self) -> None:
        states = {
            "postgresql": is_sys_service_active("postgresql"),
            "mysql": is_sys_service_active("mysql"),
            "focus": FOCUS_FLAG.exists(),
            "viz": is_sys_service_active("hollow-visualizer.service", user=True),
        }
        for key, active in states.items():
            btn, slbl = self.svc_cards[key]
            ctx = btn.get_style_context()
            if active:
                ctx.add_class("running")
                slbl.set_text("● Aktif (Hemat Baterai)" if key == "focus" else "● Running")
            else:
                ctx.remove_class("running")
                slbl.set_text("○ Normal" if key == "focus" else "○ Stopped")

        ports = get_listening_ports()
        if ports:
            txt = "   ".join(f":{p} ({name})" for p, name in ports)
        else:
            txt = "Tidak ada port lokal yang sedang listening."
        self.ports_lbl.set_text(txt)

    def _toggle_service(self, key: str) -> None:
        if key in ("postgresql", "mysql"):
            active = is_sys_service_active(key)
            action = "stop" if active else "start"
            self.status_lbl.set_text(f"Menjalankan {action} {key}...")

            def worker():
                subprocess.run(["pkexec", "systemctl", action, key], check=False)
                GLib.idle_add(self._refresh_dev)
                GLib.idle_add(self.status_lbl.set_text, f"{key}: {action} selesai.")

            threading.Thread(target=worker, daemon=True).start()
            return

        if key == "viz":
            active = is_sys_service_active("hollow-visualizer.service", user=True)
            subprocess.run(["systemctl", "--user", "stop" if active else "start", "hollow-visualizer.service"], check=False)
            self._refresh_dev()
            return

        if key == "focus":
            FOCUS_FLAG.parent.mkdir(parents=True, exist_ok=True)
            if FOCUS_FLAG.exists():
                FOCUS_FLAG.unlink()
                for svc in HEAVY_USER_SERVICES:
                    subprocess.run(["systemctl", "--user", "start", svc], check=False)
                self.status_lbl.set_text("Mode Fokus dimatikan — wallpaper & efek hidup kembali.")
            else:
                FOCUS_FLAG.write_text("1\n", encoding="utf-8")
                for svc in HEAVY_USER_SERVICES:
                    subprocess.run(["systemctl", "--user", "stop", svc], check=False)
                self.status_lbl.set_text("Mode Fokus aktif — live wallpaper, partikel & visualizer dijeda.")
            self._refresh_dev()

    def _build_clip_tab(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.clip_search = Gtk.Entry()
        self.clip_search.set_placeholder_text("Cari riwayat copy-paste...")
        self.clip_search.connect("changed", lambda _e: self._refresh_clipboard())
        self.clip_search.connect("activate", self._copy_first_match)
        top.pack_start(self.clip_search, True, True, 0)

        btn_clear = Gtk.Button(label="Bersihkan")
        btn_clear.get_style_context().add_class("close-btn")
        btn_clear.connect("clicked", self._clear_clipboard)
        top.pack_end(btn_clear, False, False, 0)
        box.pack_start(top, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.clip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.clip_box.get_style_context().add_class("clip-list")
        scroll.add(self.clip_box)
        box.pack_start(scroll, True, True, 0)

        self.filtered_clips: List[str] = []
        self.stack.add_named(box, "clip")

    def _refresh_clipboard(self) -> None:
        for child in self.clip_box.get_children():
            self.clip_box.remove(child)
        q = self.clip_search.get_text().strip().lower()
        items = load_clipboard_items()
        self.filtered_clips = []
        for it in items:
            txt = str(it.get("text", ""))
            if q and q not in txt.lower():
                continue
            self.filtered_clips.append(txt)
            preview = " ".join(txt.splitlines())
            if len(preview) > 76:
                preview = preview[:73] + "..."
            btn = Gtk.Button(label=preview)
            btn.get_style_context().add_class("clip-row")
            btn.get_child().set_halign(Gtk.Align.START)
            btn.connect("clicked", lambda _b, t=txt: self._select_clip(t))
            self.clip_box.pack_start(btn, False, False, 0)

        if not self.filtered_clips:
            empty = Gtk.Label(label="Belum ada riwayat clipboard (coba copy teks dulu).")
            empty.get_style_context().add_class("sub-lbl")
            empty.set_margin_top(24)
            self.clip_box.pack_start(empty, False, False, 0)
        self.clip_box.show_all()

    def _copy_first_match(self, _e) -> None:
        if self.filtered_clips:
            self._select_clip(self.filtered_clips[0])

    def _select_clip(self, text: str) -> None:
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text(text, -1)
        cb.store()
        self.status_lbl.set_text("Tersalin ke clipboard! Siap Ctrl+V.")
        GLib.timeout_add(160, lambda: (self.destroy(), False)[1])

    def _clear_clipboard(self, _b) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CLIP_FILE.write_text("[]\n", encoding="utf-8")
        self._refresh_clipboard()
        self.status_lbl.set_text("Riwayat clipboard dibersihkan.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hollow Purple Dev & Clipboard Panel")
    parser.add_argument("--tab", choices=["dev", "clip"], default="dev")
    args = parser.parse_args()

    # Infer default tab from invoked symlink name (`clip-panel` vs `dev-panel`)
    prog = Path(sys.argv[0]).name
    tab = "clip" if "clip" in prog else args.tab

    os.environ.setdefault("GDK_BACKEND", "wayland")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    HollowPanelWindow(initial_tab=tab)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
