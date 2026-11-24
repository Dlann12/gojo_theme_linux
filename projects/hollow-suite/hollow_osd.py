#!/usr/bin/env python3
"""
hollow-osd: Hollow Purple Glass Volume & Brightness HUD (Wayland Layer-Shell).
Listens to real PipeWire/PulseAudio volume/mute changes via `pactl subscribe`
and backlight sysfs brightness changes, showing a sleek 100% click-through neon pill.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import cairo
import gi
import numpy as np

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

SERVICE_NAME = "hollow-osd.service"
TRIGGER_FILE = Path.home() / ".config" / "hollow-suite" / "osd_trigger"

LAYER_OVERLAY = 3
EDGE_BOTTOM = 3
KB_NONE = 0

W = 324
H = 62


class _PyGObjectStruct(ctypes.Structure):
    _fields_ = [("ob_refcnt", ctypes.c_ssize_t), ("ob_type", ctypes.c_void_p), ("obj", ctypes.c_void_p)]


def _gobject_ptr(obj: object) -> int:
    return _PyGObjectStruct.from_address(id(obj)).obj


_libgdk = ctypes.CDLL("libgdk-3.so.0")
_libcairo = ctypes.CDLL("libcairo.so.2")
_libcairo.cairo_region_create.restype = ctypes.c_void_p
_libcairo.cairo_region_destroy.argtypes = [ctypes.c_void_p]
_libgdk.gdk_window_input_shape_combine_region.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int
]


def _setup_layer_shell(win: Gtk.Window) -> None:
    try:
        lib = ctypes.CDLL("libgtk-layer-shell.so.0")
        lib.gtk_layer_is_supported.restype = ctypes.c_bool
        if not lib.gtk_layer_is_supported():
            return
        lib.gtk_layer_init_for_window.argtypes = [ctypes.c_void_p]
        lib.gtk_layer_set_layer.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_anchor.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_bool]
        lib.gtk_layer_set_margin.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        lib.gtk_layer_set_exclusive_zone.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_keyboard_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_namespace.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        ptr = _gobject_ptr(win)
        lib.gtk_layer_init_for_window(ptr)
        lib.gtk_layer_set_namespace(ptr, b"hollow-glass-osd")
        lib.gtk_layer_set_layer(ptr, LAYER_OVERLAY)
        lib.gtk_layer_set_anchor(ptr, EDGE_BOTTOM, True)
        lib.gtk_layer_set_margin(ptr, EDGE_BOTTOM, 84)
        lib.gtk_layer_set_exclusive_zone(ptr, 0)
        lib.gtk_layer_set_keyboard_mode(ptr, KB_NONE)
    except OSError:
        pass


def get_volume_state() -> Tuple[int, bool]:
    try:
        vol_out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"], text=True, stderr=subprocess.DEVNULL
        )
        m = re.search(r"(\d+)%", vol_out)
        pct = min(150, int(m.group(1))) if m else 50
        mute_out = subprocess.check_output(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"], text=True, stderr=subprocess.DEVNULL
        )
        muted = "yes" in mute_out.lower()
        return pct, muted
    except Exception:
        return 50, False


def find_backlight() -> Optional[Tuple[Path, int]]:
    bl_root = Path("/sys/class/backlight")
    if not bl_root.exists():
        return None
    for d in sorted(bl_root.iterdir()):
        bp = d / "brightness"
        mp = d / "max_brightness"
        if bp.exists() and mp.exists():
            try:
                mx = max(1, int(mp.read_text().strip()))
                return bp, mx
            except Exception:
                pass
    return None


def cairo_to_pixbuf(surf: cairo.ImageSurface, rgba_buf: np.ndarray) -> Tuple[GdkPixbuf.Pixbuf, bytes]:
    w, h = surf.get_width(), surf.get_height()
    surf.flush()
    arr = np.frombuffer(surf.get_data(), dtype=np.uint8).reshape((h, w, 4))
    rgba_buf.fill(0)
    a = arr[:, :, 3]
    mask = a > 0
    if np.any(mask):
        inv = 255.0 / a[mask].astype(np.float32)
        rgba_buf[mask, 0] = np.clip(arr[mask, 2] * inv, 0, 255).astype(np.uint8)
        rgba_buf[mask, 1] = np.clip(arr[mask, 1] * inv, 0, 255).astype(np.uint8)
        rgba_buf[mask, 2] = np.clip(arr[mask, 0] * inv, 0, 255).astype(np.uint8)
        rgba_buf[mask, 3] = a[mask]
    raw = rgba_buf.tobytes()
    pb = GdkPixbuf.Pixbuf.new_from_data(raw, GdkPixbuf.Colorspace.RGB, True, 8, w, h, w * 4)
    return pb, raw


def draw_round_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def draw_speaker_icon(cr: cairo.Context, cx: float, cy: float, muted: bool, level: int, alpha: float) -> None:
    cr.save()
    cr.translate(cx, cy)
    if muted or level == 0:
        cr.set_source_rgba(0.97, 0.44, 0.44, alpha)
    else:
        cr.set_source_rgba(0.76, 0.52, 0.99, alpha)
    # Speaker body
    cr.move_to(-10, -4)
    cr.line_to(-5, -4)
    cr.line_to(1, -9)
    cr.line_to(1, 9)
    cr.line_to(-5, 4)
    cr.line_to(-10, 4)
    cr.close_path()
    cr.fill()

    cr.set_line_width(2.0)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    if muted or level == 0:
        cr.move_to(5, -4)
        cr.line_to(11, 4)
        cr.move_to(11, -4)
        cr.line_to(5, 4)
        cr.stroke()
    else:
        if level > 10:
            cr.arc(2, 0, 5.5, -0.7, 0.7)
            cr.stroke()
        if level > 50:
            cr.set_source_rgba(0.22, 0.74, 0.97, alpha)
            cr.arc(2, 0, 9.5, -0.75, 0.75)
            cr.stroke()
    cr.restore()


def draw_sun_icon(cr: cairo.Context, cx: float, cy: float, alpha: float) -> None:
    cr.save()
    cr.translate(cx, cy)
    cr.set_source_rgba(0.98, 0.75, 0.14, alpha)
    cr.arc(0, 0, 5.2, 0, math.tau)
    cr.fill()
    cr.set_line_width(2.0)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for i in range(8):
        ang = i * math.tau / 8.0
        cr.move_to(math.cos(ang) * 8.0, math.sin(ang) * 8.0)
        cr.line_to(math.cos(ang) * 10.8, math.sin(ang) * 10.8)
    cr.stroke()
    cr.restore()


class HollowOsdWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_default_size(W, H)
        self.set_size_request(W, H)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        css = Gtk.CssProvider()
        css.load_from_data(b"window, image { background-color: transparent; background: none; }")
        Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        _setup_layer_shell(self)

        self._surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        self._rgba_buf = np.zeros((H, W, 4), dtype=np.uint8)
        self._pixbuf_ref: Optional[bytes] = None
        self.img = Gtk.Image()
        self.add(self.img)

        self.kind: str = "volume"  # "volume" | "brightness"
        self.value: int = 50
        self.smooth_val: float = 50.0
        self.muted: bool = False
        self.show_until: float = 0.0
        self.visible_now: bool = False
        self._stop = threading.Event()
        self._last_trigger_mtime = TRIGGER_FILE.stat().st_mtime if TRIGGER_FILE.exists() else 0.0

        self.connect("realize", self._make_click_through)
        self.connect("destroy", self._on_destroy)
        self.hide()

        threading.Thread(target=self._watch_volume, daemon=True).start()
        threading.Thread(target=self._watch_brightness, daemon=True).start()
        GLib.timeout_add(33, self.on_tick)

    def _make_click_through(self, *_args) -> None:
        gdk_win = self.get_window()
        if gdk_win is None:
            return
        empty = _libcairo.cairo_region_create()
        _libgdk.gdk_window_input_shape_combine_region(_gobject_ptr(gdk_win), empty, 0, 0)
        _libcairo.cairo_region_destroy(empty)

    def _on_destroy(self, *_args) -> None:
        self._stop.set()
        Gtk.main_quit()

    def trigger(self, kind: str, value: int, muted: bool = False) -> None:
        self.kind = kind
        self.value = value
        self.muted = muted
        if not self.visible_now:
            self.smooth_val = float(value)
        self.show_until = time.time() + 1.65

    def _watch_volume(self) -> None:
        last_state = get_volume_state()
        while not self._stop.is_set():
            proc = None
            try:
                proc = subprocess.Popen(
                    ["pactl", "subscribe"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    if self._stop.is_set():
                        break
                    if "on sink" in line and "change" in line:
                        cur = get_volume_state()
                        if cur != last_state:
                            last_state = cur
                            GLib.idle_add(self.trigger, "volume", cur[0], cur[1])
            except Exception:
                time.sleep(2.0)
            finally:
                if proc is not None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

    def _watch_brightness(self) -> None:
        bl = find_backlight()
        if bl is None:
            return
        bpath, bmax = bl
        try:
            last_raw = int(bpath.read_text().strip())
        except Exception:
            last_raw = bmax
        while not self._stop.is_set():
            time.sleep(0.12)
            try:
                cur_raw = int(bpath.read_text().strip())
                if cur_raw != last_raw:
                    last_raw = cur_raw
                    pct = int(round((cur_raw / bmax) * 100))
                    GLib.idle_add(self.trigger, "brightness", pct, False)
            except Exception:
                time.sleep(1.0)

    def on_tick(self) -> bool:
        now = time.time()
        # Allow CLI `hollow-osd test` to preview the pill immediately
        if TRIGGER_FILE.exists():
            try:
                mt = TRIGGER_FILE.stat().st_mtime
                if mt > self._last_trigger_mtime:
                    self._last_trigger_mtime = mt
                    vol, muted = get_volume_state()
                    self.trigger("volume", vol, muted)
            except OSError:
                pass

        remaining = self.show_until - now
        if remaining <= 0:
            if self.visible_now:
                self.visible_now = False
                self.hide()
            return True

        if not self.visible_now:
            self.visible_now = True
            self.show_all()
            self._make_click_through()

        self.smooth_val += (float(self.value) - self.smooth_val) * 0.35
        fade = min(1.0, remaining / 0.35)
        self._render(fade)
        return True

    def _render(self, alpha: float) -> None:
        cr = cairo.Context(self._surf)
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.restore()

        pad = 6.0
        pw, ph = W - pad * 2, H - pad * 2
        r = ph * 0.5

        # Translucent dark glass pill
        draw_round_rect(cr, pad, pad, pw, ph, r)
        cr.set_source_rgba(0.055, 0.06, 0.11, 0.90 * alpha)
        cr.fill_preserve()

        if self.kind == "brightness":
            cr.set_source_rgba(0.98, 0.75, 0.14, 0.65 * alpha)
        elif self.muted or self.value == 0:
            cr.set_source_rgba(0.97, 0.44, 0.44, 0.65 * alpha)
        else:
            cr.set_source_rgba(0.75, 0.52, 0.99, 0.65 * alpha)
        cr.set_line_width(1.5)
        cr.stroke()

        # Icon on left
        if self.kind == "brightness":
            draw_sun_icon(cr, pad + 26, H * 0.5, alpha)
        else:
            draw_speaker_icon(cr, pad + 26, H * 0.5, self.muted, self.value, alpha)

        # Progress track
        bx = pad + 48
        bw = pw - 108
        bh = 9.0
        by = (H - bh) * 0.5
        draw_round_rect(cr, bx, by, bw, bh, bh * 0.5)
        cr.set_source_rgba(0.58, 0.64, 0.72, 0.22 * alpha)
        cr.fill()

        # Filled gradient bar
        frac = 0.0 if (self.kind == "volume" and self.muted) else max(0.0, min(1.0, self.smooth_val / 100.0))
        fw = bw * frac
        if fw > 2.0:
            draw_round_rect(cr, bx, by, fw, bh, min(bh * 0.5, fw * 0.5))
            grad = cairo.LinearGradient(bx, 0, bx + bw, 0)
            if self.kind == "brightness":
                grad.add_color_stop_rgba(0.0, 0.96, 0.62, 0.04, alpha)
                grad.add_color_stop_rgba(1.0, 0.99, 0.90, 0.54, alpha)
            else:
                grad.add_color_stop_rgba(0.0, 0.49, 0.23, 0.93, alpha)
                grad.add_color_stop_rgba(0.55, 0.75, 0.52, 0.99, alpha)
                grad.add_color_stop_rgba(1.0, 0.22, 0.74, 0.97, alpha)
            cr.set_source(grad)
            cr.fill()

        # Percentage / MUTE label
        label = "MUTE" if (self.kind == "volume" and self.muted) else f"{int(round(self.value))}%"
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13.0)
        ext = cr.text_extents(label)
        cr.set_source_rgba(0.94, 0.96, 1.0, 0.96 * alpha)
        tx = pad + pw - 16 - ext.width - ext.x_bearing
        ty = H * 0.5 - ext.height * 0.5 - ext.y_bearing
        cr.move_to(tx, ty)
        cr.show_text(label)

        pb, raw = cairo_to_pixbuf(self._surf, self._rgba_buf)
        self._pixbuf_ref = raw
        self.img.set_from_pixbuf(pb)


def main() -> int:
    parser = argparse.ArgumentParser(prog="osd", description="Hollow Purple Volume & Brightness Glass HUD")
    parser.add_argument("command", nargs="?", choices=["daemon", "test", "status", "start", "stop"], default="status")
    args = parser.parse_args()

    if args.command == "daemon":
        os.environ.setdefault("GDK_BACKEND", "wayland")
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
        HollowOsdWindow()
        Gtk.main()
        return 0

    if args.command == "test":
        TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRIGGER_FILE.write_text(str(time.time()), encoding="utf-8")
        print("Glass HUD dipicu di bagian bawah layar!")
        return 0

    if args.command == "start":
        subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=False)
        print("Hollow Glass HUD: AKTIF.")
        return 0

    if args.command == "stop":
        subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], check=False)
        print("Hollow Glass HUD: BERHENTI.")
        return 0

    act = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME], check=False).returncode == 0
    print(f"Hollow Volume/Brightness Glass HUD: {'AKTIF' if act else 'BERHENTI'}")
    print("  Ketik `osd test` untuk melihat preview langsung, atau tekan tombol volume/brightness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
