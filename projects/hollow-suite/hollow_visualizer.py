#!/usr/bin/env python3
"""
hollow-viz: Live Neon Hollow Purple Audio Visualizer for Pop!_OS COSMIC (Wayland Layer-Shell).
Reads real system audio output via `parec` (.monitor sink), computes 36-band log FFT,
renders smooth neon bars or glowing wave at the bottom of the desktop, and sleeps at 0% CPU when silent.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import signal
import subprocess
import sys
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

CONFIG_DIR = Path.home() / ".config" / "hollow-suite"
VIZ_CONFIG = CONFIG_DIR / "visualizer.json"
SERVICE_NAME = "hollow-visualizer.service"

LAYER_BOTTOM = 1
EDGE_BOTTOM = 3
KB_NONE = 0

SURF_H = 128
NUM_BANDS = 36
SAMPLE_RATE = 44100
CHUNK_SAMPLES = 1024


class _PyGObjectStruct(ctypes.Structure):
    _fields_ = [
        ("ob_refcnt", ctypes.c_ssize_t),
        ("ob_type", ctypes.c_void_p),
        ("obj", ctypes.c_void_p),
    ]


def _gobject_ptr(obj: object) -> int:
    return _PyGObjectStruct.from_address(id(obj)).obj


_libgdk = ctypes.CDLL("libgdk-3.so.0")
_libcairo = ctypes.CDLL("libcairo.so.2")
_libcairo.cairo_region_create.restype = ctypes.c_void_p
_libcairo.cairo_region_destroy.argtypes = [ctypes.c_void_p]
_libgdk.gdk_window_input_shape_combine_region.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int
]


def _load_layer_shell() -> Optional[ctypes.CDLL]:
    try:
        lib = ctypes.CDLL("libgtk-layer-shell.so.0")
        lib.gtk_layer_is_supported.restype = ctypes.c_bool
        lib.gtk_layer_init_for_window.argtypes = [ctypes.c_void_p]
        lib.gtk_layer_set_layer.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_anchor.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_bool]
        lib.gtk_layer_set_margin.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        lib.gtk_layer_set_exclusive_zone.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_keyboard_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.gtk_layer_set_namespace.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        return lib
    except OSError:
        return None


def load_viz_config() -> dict:
    if VIZ_CONFIG.exists():
        try:
            d = json.loads(VIZ_CONFIG.read_text(encoding="utf-8"))
            if d.get("mode") in ("bars", "wave"):
                return d
        except (OSError, json.JSONDecodeError):
            pass
    return {"mode": "bars"}


def save_viz_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    VIZ_CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get_monitor_source() -> str:
    try:
        sink = subprocess.check_output(
            ["pactl", "get-default-sink"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if sink:
            return f"{sink}.monitor"
    except Exception:
        pass
    return "@DEFAULT_MONITOR@"


class AudioSpectrumReader:
    """Streams real system audio via `parec` and maintains a 36-band log FFT spectrum."""

    def __init__(self, bands: int = NUM_BANDS) -> None:
        self.bands = bands
        self.levels = np.zeros(bands, dtype=np.float32)
        self.last_active_ts: float = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._window = np.hanning(CHUNK_SAMPLES).astype(np.float32)

        # Logarithmic frequency bins between 45 Hz and 11,000 Hz
        freqs = np.fft.rfftfreq(CHUNK_SAMPLES, 1.0 / SAMPLE_RATE)
        edges = np.geomspace(45.0, 11000.0, bands + 1)
        self._bin_slices = []
        for i in range(bands):
            lo = int(np.searchsorted(freqs, edges[i]))
            hi = max(lo + 1, int(np.searchsorted(freqs, edges[i + 1])))
            self._bin_slices.append((lo, min(hi, len(freqs))))

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def get_levels(self) -> Tuple[np.ndarray, bool]:
        with self._lock:
            active = (time.time() - self.last_active_ts) < 1.8
            return self.levels.copy(), active

    def _run(self) -> None:
        chunk_bytes = CHUNK_SAMPLES * 2
        while not self._stop.is_set():
            src = get_monitor_source()
            proc = None
            try:
                proc = subprocess.Popen(
                    [
                        "parec",
                        f"--device={src}",
                        f"--rate={SAMPLE_RATE}",
                        "--channels=1",
                        "--format=s16le",
                        "--latency-msec=25",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                assert proc.stdout is not None
                while not self._stop.is_set():
                    data = proc.stdout.read(chunk_bytes)
                    if not data or len(data) < chunk_bytes:
                        break
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(samples * samples)))
                    if rms > 0.0018:
                        spec = np.abs(np.fft.rfft(samples * self._window))
                        raw = np.zeros(self.bands, dtype=np.float32)
                        for i, (lo, hi) in enumerate(self._bin_slices):
                            val = float(np.mean(spec[lo:hi]))
                            # Slight treble lift + soft log compression
                            boost = 1.0 + (i / self.bands) * 1.4
                            raw[i] = min(1.0, math.log1p(val * boost * 0.45) / 2.6)
                        with self._lock:
                            self.levels = raw
                            self.last_active_ts = time.time()
                    else:
                        with self._lock:
                            self.levels *= 0.80
            except Exception:
                time.sleep(1.5)
            finally:
                if proc is not None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1)
                    except Exception:
                        pass


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


class VisualizerWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        css = Gtk.CssProvider()
        css.load_from_data(b"window, image { background-color: transparent; background: none; }")
        Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        mon_w = 1920
        try:
            disp = Gdk.Display.get_default()
            if disp and disp.get_n_monitors() > 0:
                mon_w = max(800, disp.get_monitor(0).get_geometry().width)
        except Exception:
            pass
        self.win_w = min(1040, mon_w - 80)
        self.win_h = SURF_H
        self.set_default_size(self.win_w, self.win_h)
        self.set_size_request(self.win_w, self.win_h)

        lib = _load_layer_shell()
        if lib and lib.gtk_layer_is_supported():
            ptr = _gobject_ptr(self)
            lib.gtk_layer_init_for_window(ptr)
            lib.gtk_layer_set_namespace(ptr, b"hollow-audio-visualizer")
            lib.gtk_layer_set_layer(ptr, LAYER_BOTTOM)
            lib.gtk_layer_set_anchor(ptr, EDGE_BOTTOM, True)
            lib.gtk_layer_set_margin(ptr, EDGE_BOTTOM, 10)
            lib.gtk_layer_set_exclusive_zone(ptr, 0)
            lib.gtk_layer_set_keyboard_mode(ptr, KB_NONE)

        self.reader = AudioSpectrumReader(NUM_BANDS)
        self.smooth = np.zeros(NUM_BANDS, dtype=np.float32)
        self.mode = load_viz_config().get("mode", "bars")
        self._last_cfg_check = 0.0
        self.currently_visible = False

        self._surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.win_w, self.win_h)
        self._rgba_buf = np.zeros((self.win_h, self.win_w, 4), dtype=np.uint8)
        self._pixbuf_ref: Optional[bytes] = None

        self.img = Gtk.Image()
        self.add(self.img)
        self.connect("realize", self._make_click_through)
        self.connect("destroy", self._on_destroy)

        self.hide()
        GLib.timeout_add(34, self.on_tick)

    def _make_click_through(self, *_args) -> None:
        gdk_win = self.get_window()
        if gdk_win is None:
            return
        empty = _libcairo.cairo_region_create()
        _libgdk.gdk_window_input_shape_combine_region(_gobject_ptr(gdk_win), empty, 0, 0)
        _libcairo.cairo_region_destroy(empty)

    def _on_destroy(self, *_args) -> None:
        self.reader.stop()
        Gtk.main_quit()

    def on_tick(self) -> bool:
        now = time.time()
        if now - self._last_cfg_check > 1.0:
            self._last_cfg_check = now
            self.mode = load_viz_config().get("mode", "bars")

        raw, active = self.reader.get_levels()

        # Fast attack, smooth decay
        for i in range(NUM_BANDS):
            if raw[i] > self.smooth[i]:
                self.smooth[i] += (raw[i] - self.smooth[i]) * 0.45
            else:
                self.smooth[i] *= 0.84

        has_energy = active or float(self.smooth.max()) > 0.015
        if has_energy != self.currently_visible:
            self.currently_visible = has_energy
            if has_energy:
                self.show_all()
                self._make_click_through()
            else:
                self.hide()

        if self.currently_visible:
            self._render()
        return True

    def _render(self) -> None:
        cr = cairo.Context(self._surf)
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.restore()

        w, h = self.win_w, self.win_h
        floor_y = h - 24.0
        max_bar_h = floor_y - 12.0

        # Mirror bass cleanly toward center for balanced Hollow Purple aesthetic
        half = NUM_BANDS // 2
        mirrored = np.concatenate([self.smooth[:half][::-1], self.smooth[:half]])

        if self.mode == "wave":
            grad = cairo.LinearGradient(0, 0, w, 0)
            grad.add_color_stop_rgba(0.0, 0.22, 0.74, 0.97, 0.92)
            grad.add_color_stop_rgba(0.5, 0.75, 0.52, 0.99, 0.98)
            grad.add_color_stop_rgba(1.0, 0.93, 0.29, 0.60, 0.92)

            # Soft glow stroke
            cr.set_source_rgba(0.66, 0.34, 0.98, 0.28)
            cr.set_line_width(10.0)
            self._trace_wave(cr, mirrored, w, floor_y, max_bar_h)
            cr.stroke()

            cr.set_source(grad)
            cr.set_line_width(3.2)
            self._trace_wave(cr, mirrored, w, floor_y, max_bar_h)
            cr.stroke()
        else:
            n = len(mirrored)
            gap = 7.0
            bw = (w - gap * (n + 1)) / n
            grad = cairo.LinearGradient(0, floor_y, 0, 10)
            grad.add_color_stop_rgba(0.0, 0.49, 0.23, 0.93, 0.90)
            grad.add_color_stop_rgba(0.55, 0.75, 0.52, 0.99, 0.95)
            grad.add_color_stop_rgba(1.0, 0.22, 0.74, 0.97, 0.98)

            for i, val in enumerate(mirrored):
                bh = max(4.0, float(val) * max_bar_h)
                x = gap + i * (bw + gap)
                y = floor_y - bh
                r = min(5.0, bw * 0.45, bh * 0.45)

                # Main neon bar
                cr.set_source(grad)
                self._round_rect(cr, x, y, bw, bh, r)
                cr.fill()

                # Floor reflection
                cr.set_source_rgba(0.68, 0.45, 1.0, 0.22)
                self._round_rect(cr, x, floor_y + 4, bw, min(18.0, bh * 0.24), 2.5)
                cr.fill()

        pb, raw = cairo_to_pixbuf(self._surf, self._rgba_buf)
        self._pixbuf_ref = raw
        self.img.set_from_pixbuf(pb)

    @staticmethod
    def _trace_wave(cr: cairo.Context, vals: np.ndarray, w: int, floor_y: float, max_h: float) -> None:
        n = len(vals)
        for i, v in enumerate(vals):
            x = (i / (n - 1)) * w
            y = floor_y - 6.0 - float(v) * max_h
            if i == 0:
                cr.move_to(x, y)
            else:
                px = ((i - 1) / (n - 1)) * w
                py = floor_y - 6.0 - float(vals[i - 1]) * max_h
                mx = (px + x) * 0.5
                cr.curve_to(mx, py, mx, y, x, y)

    @staticmethod
    def _round_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()


def main() -> int:
    parser = argparse.ArgumentParser(prog="viz", description="Hollow Purple Live Audio Visualizer")
    parser.add_argument("command", nargs="?", choices=["daemon", "status", "start", "stop", "mode"], default="status")
    parser.add_argument("value", nargs="?", help="bars | wave")
    args = parser.parse_args()

    if args.command == "daemon":
        os.environ.setdefault("GDK_BACKEND", "wayland")
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
        VisualizerWindow()
        Gtk.main()
        return 0

    if args.command == "mode":
        if args.value not in ("bars", "wave"):
            print("Gunakan: viz mode <bars|wave>")
            return 1
        cfg = load_viz_config()
        cfg["mode"] = args.value
        save_viz_config(cfg)
        print(f"Mode visualizer diubah ke: {args.value}")
        return 0

    if args.command == "start":
        subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=False)
        print("Hollow Audio Visualizer: AKTIF (otomatis muncul saat musik/audio diputar).")
        return 0

    if args.command == "stop":
        subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], check=False)
        print("Hollow Audio Visualizer: BERHENTI.")
        return 0

    act = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME], check=False).returncode == 0
    mode = load_viz_config().get("mode", "bars")
    print(f"♫ Hollow Audio Visualizer: {'AKTIF' if act else 'BERHENTI'} | Mode: {mode}")
    print("  Gunakan: viz mode bars|wave  ·  viz start|stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
