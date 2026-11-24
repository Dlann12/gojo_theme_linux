#!/usr/bin/env python3
"""
cli-pet HD Overlay: Full-resolution 3D OpenPets spritesheet companion for terminal.
Auto-discovers Gojo + all pets installed in ~/.config/OpenPets/pets/
(e.g. via `npx -y install-pet <slug>`).

Appears automatically ONLY when a terminal window is focused on Pop!_OS COSMIC
via Wayland `ext_foreign_toplevel_list_v1` + `zcosmic_toplevel_info_v1`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import random
import select
import signal
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cairo
import gi
import numpy as np
from PIL import Image

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

BASE_DIR = Path(__file__).resolve().parent
LOCAL_ASSETS_DIR = BASE_DIR / "assets"
OPENPETS_DIR = Path.home() / ".config" / "OpenPets" / "pets"
STATE_DIR = Path.home() / ".config" / "cli-pet"
STATE_FILE = STATE_DIR / "state.json"
HIDDEN_FILE = STATE_DIR / "hidden"

# gtk-layer-shell constants
LAYER_TOP = 2
EDGE_BOTTOM = 3
KB_NONE = 0

SURF_H = 216
FLOOR_Y = 184.0
PET_H = 138

TERMINAL_KEYWORDS = (
    "cosmicterm", "cosmic-term", "terminal", "alacritty", "kitty",
    "ghostty", "wezterm", "konsole", "tilix", "foot", "terminator",
    "xterm", "urxvt", "rio", "warp", "tabby", "hyper", "guake", "yakuake",
)

# Signature floor glow RGB & personality quotes per pet id
PET_PERSONALITIES: Dict[str, dict] = {
    "gojo-52f9": {
        "glow": (0.68, 0.45, 1.00),
        "idle": [
            "tenang, aku yang terkuat~",
            "Domain Expansion: No Bugs!",
            "Infinity aktif, error mental~",
            "hehe~ gampang banget nih",
            "semangat ngodingnya!",
        ],
        "pet": ["hei, rambutku berantakan nih~", "hehe~ mantap!", "yo! *senyum santai*"],
        "feed": ["manis banget! kikufuku favoritku~!", "mantap, energi balik lagi!"],
    },
    "halloween-ghost": {
        "glow": (0.52, 0.88, 1.00),
        "idle": [
            "booo~ aku hantu ramah!",
            "bug-nya serem nggak?",
            "melayang nemenin ngoding~",
            "hiihihi~ semangat ya!",
        ],
        "pet": ["ih geli~ hihihi!", "aku suka dielus~", "boo~ hehe!"],
        "feed": ["permen halloween! nyam~", "enak banget~"],
    },
    "vincent-hamster": {
        "glow": (1.00, 0.76, 0.32),
        "idle": [
            "squeak! semangat ngoding!",
            "ngemil kuaci dulu yuk~",
            "kode kita keren banget!",
            "jangan lupa commit ya~",
        ],
        "pet": ["squeak squeak! nyaman~", "pipiku gembul ya~", "lagi dong~"],
        "feed": ["nyam nyam kuaci favorit!", "pipi penuh camilan~"],
    },
    "cache-capy": {
        "glow": (0.45, 0.88, 0.72),
        "idle": [
            "santai aja... cache hit~",
            "build aman, tenang~",
            "chill dulu sebentar yuk~",
            "no rush, yang penting rapi~",
        ],
        "pet": ["hmm... adem banget~", "santai... nyaman~", "capy happy~"],
        "feed": ["nyam~ jeruk yuzu enak!", "tenang dan kenyang~"],
    },
}

DEFAULT_PERSONALITY = {
    "glow": (0.58, 0.78, 1.00),
    "idle": ["semangat ngodingnya~", "aku nemenin di sini!", "jangan lupa istirahat ya~"],
    "pet": ["terima kasih~", "nyaman banget~"],
    "feed": ["nyam nyam! enak banget!", "makasih camilannya~"],
}

PLAY_QUOTES = [
    "yeay! tangkap orb-nya!",
    "hup! kena~",
    "seru banget! *hop*",
]


class _PyGObjectStruct(ctypes.Structure):
    _fields_ = [
        ("ob_refcnt", ctypes.c_ssize_t),
        ("ob_type", ctypes.c_void_p),
        ("obj", ctypes.c_void_p),
    ]


class _CairoRectInt(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
    ]


def _gobject_ptr(obj: object) -> int:
    return _PyGObjectStruct.from_address(id(obj)).obj


_libgdk = ctypes.CDLL("libgdk-3.so.0")
_libcairo = ctypes.CDLL("libcairo.so.2")
_libcairo.cairo_region_create.restype = ctypes.c_void_p
_libcairo.cairo_region_union_rectangle.argtypes = [ctypes.c_void_p, ctypes.POINTER(_CairoRectInt)]
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


def _is_terminal_app_id(app_id: str) -> bool:
    low = (app_id or "").lower()
    return any(k in low for k in TERMINAL_KEYWORDS)


class CosmicFocusWatcher:
    """Real-time zero-polling Wayland active window watcher for Pop!_OS COSMIC."""

    def __init__(self) -> None:
        self.terminal_focused: bool = False
        self.active_app_id: str = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _wl_str(s: str) -> bytes:
        b = s.encode("utf-8") + b"\x00"
        pad = (4 - (len(b) % 4)) % 4
        return struct.pack("<I", len(b)) + b + b"\x00" * pad

    @staticmethod
    def _unpack_str(payload: bytes, off: int = 0) -> Tuple[str, int]:
        if len(payload) < off + 4:
            return "", len(payload)
        slen = struct.unpack("<I", payload[off:off + 4])[0]
        if slen == 0 or len(payload) < off + 4 + slen:
            return "", len(payload)
        s = payload[off + 4:off + 4 + slen - 1].decode("utf-8", errors="replace")
        pad = (4 - (slen % 4)) % 4
        return s, off + 4 + slen + pad

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._watch_once()
            except Exception:
                time.sleep(1.5)

    def _watch_once(self) -> None:
        disp = os.environ.get("WAYLAND_DISPLAY", "wayland-1")
        rt = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(rt, disp)
        if not os.path.exists(sock_path):
            time.sleep(1.5)
            return

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(sock_path)

        def send_msg(obj_id: int, opcode: int, payload: bytes = b"") -> None:
            size = 8 + len(payload)
            sock.sendall(struct.pack("<II", obj_id, (size << 16) | opcode) + payload)

        send_msg(1, 1, struct.pack("<I", 2))
        send_msg(1, 0, struct.pack("<I", 3))

        next_id = 4
        ext_id: Optional[int] = None
        cos_id: Optional[int] = None
        ext_handles: Dict[int, dict] = {}
        cos_handles: Dict[int, int] = {}
        buf = b""

        def recompute_focus() -> None:
            focused_app = ""
            is_term = False
            for info in ext_handles.values():
                if 2 in info["states"]:
                    focused_app = info["app_id"]
                    if _is_terminal_app_id(focused_app):
                        is_term = True
                        break
            self.active_app_id = focused_app
            self.terminal_focused = is_term

        try:
            while not self._stop.is_set():
                r, _, _ = select.select([sock], [], [], 0.5)
                if not r:
                    continue
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= 8:
                    oid, sw = struct.unpack("<II", buf[:8])
                    size = sw >> 16
                    op = sw & 0xFFFF
                    if size < 8 or len(buf) < size:
                        break
                    pl = buf[8:size]
                    buf = buf[size:]

                    if oid == 2 and op == 0:
                        name = struct.unpack("<I", pl[:4])[0]
                        iface, off = self._unpack_str(pl, 4)
                        ver = struct.unpack("<I", pl[off:off + 4])[0]
                        if iface == "ext_foreign_toplevel_list_v1" and ext_id is None:
                            ext_id = next_id
                            next_id += 1
                            send_msg(
                                2, 0,
                                struct.pack("<I", name)
                                + self._wl_str(iface)
                                + struct.pack("<II", min(ver, 1), ext_id),
                            )
                        elif iface == "zcosmic_toplevel_info_v1" and cos_id is None:
                            cos_id = next_id
                            next_id += 1
                            send_msg(
                                2, 0,
                                struct.pack("<I", name)
                                + self._wl_str(iface)
                                + struct.pack("<II", min(ver, 3), cos_id),
                            )
                            for hid in list(ext_handles.keys()):
                                if hid not in cos_handles.values():
                                    cid = next_id
                                    next_id += 1
                                    cos_handles[cid] = hid
                                    send_msg(cos_id, 1, struct.pack("<II", cid, hid))

                    elif ext_id is not None and oid == ext_id and op == 0:
                        hid = struct.unpack("<I", pl[:4])[0]
                        ext_handles[hid] = {"app_id": "", "title": "", "states": []}
                        if cos_id is not None:
                            cid = next_id
                            next_id += 1
                            cos_handles[cid] = hid
                            send_msg(cos_id, 1, struct.pack("<II", cid, hid))

                    elif oid in ext_handles:
                        if op == 0:
                            ext_handles.pop(oid, None)
                            for c_k, h_v in list(cos_handles.items()):
                                if h_v == oid:
                                    cos_handles.pop(c_k, None)
                            recompute_focus()
                        elif op == 1:
                            recompute_focus()
                        elif op == 2:
                            ext_handles[oid]["title"], _ = self._unpack_str(pl, 0)
                        elif op == 3:
                            ext_handles[oid]["app_id"], _ = self._unpack_str(pl, 0)
                            recompute_focus()

                    elif oid in cos_handles:
                        hid = cos_handles[oid]
                        if op == 0:
                            cos_handles.pop(oid, None)
                            ext_handles.pop(hid, None)
                            recompute_focus()
                        elif op == 8 and len(pl) >= 4 and hid in ext_handles:
                            alen = struct.unpack("<I", pl[:4])[0]
                            states = list(struct.unpack(f"<{alen // 4}I", pl[4:4 + alen]))
                            ext_handles[hid]["states"] = states
                            recompute_focus()
                        elif op == 1:
                            recompute_focus()
        finally:
            sock.close()


def pil_to_cairo_surface(im: Image.Image) -> Tuple[cairo.ImageSurface, bytearray]:
    rgba = im.convert("RGBA")
    arr = np.array(rgba, dtype=np.uint8)
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    bgra = np.empty_like(arr)
    bgra[:, :, 0] = (arr[:, :, 2] * a[:, :, 0]).astype(np.uint8)
    bgra[:, :, 1] = (arr[:, :, 1] * a[:, :, 0]).astype(np.uint8)
    bgra[:, :, 2] = (arr[:, :, 0] * a[:, :, 0]).astype(np.uint8)
    bgra[:, :, 3] = arr[:, :, 3]
    buf = bytearray(bgra.tobytes())
    surf = cairo.ImageSurface.create_for_data(
        buf, cairo.FORMAT_ARGB32, rgba.width, rgba.height, rgba.width * 4
    )
    return surf, buf


def cairo_surface_to_pixbuf(surf: cairo.ImageSurface, rgba_buf: np.ndarray) -> Tuple[GdkPixbuf.Pixbuf, bytes]:
    w = surf.get_width()
    h = surf.get_height()
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


@dataclass
class PetDef:
    pet_id: str
    display_name: str
    sheet_path: Path


def discover_pets() -> Dict[str, PetDef]:
    """Discover OpenPets spritesheets from local assets and ~/.config/OpenPets/pets/."""
    found: Dict[str, PetDef] = {}
    search_dirs: List[Path] = []
    if LOCAL_ASSETS_DIR.exists():
        search_dirs.extend(sorted(p for p in LOCAL_ASSETS_DIR.iterdir() if p.is_dir()))
    if OPENPETS_DIR.exists():
        search_dirs.extend(sorted(p for p in OPENPETS_DIR.iterdir() if p.is_dir()))

    for d in search_dirs:
        pj = d / "pet.json"
        if not pj.exists():
            continue
        try:
            meta = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = str(meta.get("id") or d.name).strip()
        name = str(meta.get("displayName") or pid).strip()
        sp = d / str(meta.get("spritesheetPath") or "spritesheet.webp")
        if sp.exists() and pid not in found:
            found[pid] = PetDef(pet_id=pid, display_name=name, sheet_path=sp)
    return found


class OpenPetSpriteBank:
    """Loads & caches universal OpenPets v1 (9-row) & v2 (11-row) 192x208 spritesheets."""

    def __init__(self) -> None:
        self._bufs: List[bytearray] = []
        self.defs: Dict[str, PetDef] = {}
        self.anims: Dict[str, Dict[str, List[cairo.ImageSurface]]] = {}
        self.reload()

    def reload(self) -> None:
        fresh = discover_pets()
        for pid, pdef in fresh.items():
            if pid not in self.anims:
                loaded = self._load_sheet(pdef.sheet_path)
                if loaded:
                    self.anims[pid] = loaded
        self.defs = {pid: pdef for pid, pdef in fresh.items() if pid in self.anims}

    def _load_sheet(self, path: Path) -> Dict[str, List[cairo.ImageSurface]]:
        try:
            sheet = Image.open(path).convert("RGBA")
        except OSError:
            return {}
        tw, th = 192, 208
        cols = max(1, sheet.width // tw)
        rows = max(1, sheet.height // th)

        row_map = {
            "idle": 0,
            "walk_right": 1,
            "walk_left": 2,
            "wave": 3,
            "play": 4,
            "sleep": 5,
            "pet": 6,
            "code": 7,
            "eat": 8,
            "stretch": 9,
            "chill": 10,
        }

        result: Dict[str, List[cairo.ImageSurface]] = {}
        for anim_name, r_idx in row_map.items():
            if r_idx >= rows:
                continue
            frames: List[cairo.ImageSurface] = []
            for c_idx in range(cols):
                tile = sheet.crop((c_idx * tw, r_idx * th, (c_idx + 1) * tw, (r_idx + 1) * th))
                arr = np.array(tile)
                if arr[:, :, 3].max() < 20:
                    continue
                if anim_name == "play":
                    cropped = tile
                else:
                    ys = np.where(arr[:, :, 3] > 20)[0]
                    y_bot = min(th, int(ys.max()) + 1)
                    cropped = tile.crop((0, 0, tw, y_bot))

                scale = PET_H / th
                nw = max(20, int(round(cropped.width * scale)))
                nh = max(20, int(round(cropped.height * scale)))
                resized = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
                surf, buf = pil_to_cairo_surface(resized)
                self._bufs.append(buf)
                frames.append(surf)
            if frames:
                result[anim_name] = frames
        return result

    def get_frame(self, pet_id: str, action: str, facing: int, phase: float) -> Optional[cairo.ImageSurface]:
        pet_anims = self.anims.get(pet_id)
        if not pet_anims:
            return None

        if action == "walk":
            key = "walk_right" if facing >= 0 else "walk_left"
            fps = 10.0
        elif action == "code":
            key = "code"
            fps = 5.5
        elif action == "pet":
            key = "pet"
            fps = 7.5
        elif action == "play":
            key = "play"
            fps = 8.5
        elif action == "sleep":
            frames = pet_anims.get("sleep") or pet_anims.get("idle", [])
            if not frames:
                return None
            idx = int(phase * 3.5)
            if idx < max(1, len(frames) - 3):
                return frames[idx]
            doze = frames[-min(3, len(frames)):]
            return doze[int(phase * 1.4) % len(doze)]
        elif action == "eat":
            key = "eat"
            fps = 5.0
        elif action == "wave":
            key = "wave"
            fps = 6.0
        elif action == "stretch":
            key = "stretch"
            fps = 5.5
        else:
            key = "idle"
            fps = 4.2

        frames = pet_anims.get(key) or pet_anims.get("idle", [])
        if not frames:
            return None
        return frames[int(phase * fps) % len(frames)]


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    kind: str
    size: float
    ttl: float
    max_ttl: float
    rgb: Tuple[float, float, float]


@dataclass
class PetState:
    active_pets: List[str] = field(default_factory=list)
    scope: str = "terminal"
    hunger: float = 85.0
    happiness: float = 88.0
    energy: float = 90.0
    xp: int = 0
    level: int = 1
    pets_count: int = 0
    feeds_count: int = 0
    born_ts: float = field(default_factory=time.time)
    last_ts: float = field(default_factory=time.time)
    last_event: str = ""
    last_event_ts: float = 0.0

    def add_xp(self, amount: int) -> bool:
        self.xp += amount
        needed = self.level * 50
        leveled = False
        while self.xp >= needed:
            self.xp -= needed
            self.level += 1
            needed = self.level * 50
            leveled = True
        return leveled

    def to_dict(self) -> dict:
        return {
            "active_pets": self.active_pets,
            "scope": self.scope,
            "hunger": round(self.hunger, 2),
            "happiness": round(self.happiness, 2),
            "energy": round(self.energy, 2),
            "xp": self.xp,
            "level": self.level,
            "pets_count": self.pets_count,
            "feeds_count": self.feeds_count,
            "born_ts": self.born_ts,
            "last_ts": self.last_ts,
            "last_event": self.last_event,
            "last_event_ts": self.last_event_ts,
        }

    @classmethod
    def load(cls, available_ids: List[str]) -> "PetState":
        if STATE_FILE.exists():
            try:
                d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                scope = str(d.get("scope", "terminal"))
                if scope not in ("terminal", "always"):
                    scope = "terminal"
                raw_active = d.get("active_pets")
                if isinstance(raw_active, list):
                    active = [p for p in raw_active if p in available_ids]
                else:
                    active = list(available_ids)
                if not active:
                    active = list(available_ids)
                return cls(
                    active_pets=active,
                    scope=scope,
                    hunger=float(d.get("hunger", 85.0)),
                    happiness=float(d.get("happiness", 88.0)),
                    energy=float(d.get("energy", 90.0)),
                    xp=int(d.get("xp", 0)),
                    level=max(1, int(d.get("level", 1))),
                    pets_count=int(d.get("pets_count", 0)),
                    feeds_count=int(d.get("feeds_count", 0)),
                    born_ts=float(d.get("born_ts", time.time())),
                    last_ts=float(d.get("last_ts", time.time())),
                    last_event=str(d.get("last_event", "")),
                    last_event_ts=float(d.get("last_event_ts", 0.0)),
                )
            except (json.JSONDecodeError, OSError, ValueError, TypeError):
                pass
        s = cls(active_pets=list(available_ids))
        s.save()
        return s

    def save(self) -> float:
        self.last_ts = time.time()
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
            tmp.replace(STATE_FILE)
            return STATE_FILE.stat().st_mtime
        except OSError:
            return 0.0


@dataclass
class Actor:
    pet_id: str
    x: float
    vx: float = 0.0
    facing: int = 1
    action: str = "idle"
    action_until: float = 0.0
    phase: float = 0.0
    width: float = 115.0
    height: float = float(PET_H)
    speech: str = ""
    speech_until: float = 0.0


class SquadWorld:
    def __init__(self, width: int, sprites: OpenPetSpriteBank, state: PetState) -> None:
        self.width = max(560, width)
        self.sprites = sprites
        self.state = state
        self.actors: Dict[str, Actor] = {}
        self.particles: List[Particle] = []
        self.ball_x: Optional[float] = None
        self.ball_y: float = FLOOR_Y - 12.0
        self.ball_vx: float = 0.0
        self.ball_vy: float = 0.0
        self.known_mtime: float = STATE_FILE.stat().st_mtime if STATE_FILE.exists() else 0.0
        self.known_event_ts: float = state.last_event_ts
        self.last_sync: float = time.time()
        self.last_save: float = time.time()
        self._ensure_actors()

    def _ensure_actors(self) -> None:
        now = time.time()
        all_ids = list(self.sprites.defs.keys())
        n = max(1, len(all_ids))
        span = self.width - 220.0
        for idx, pid in enumerate(all_ids):
            if pid not in self.actors:
                px = 110.0 + (span * (idx + 0.5) / n)
                init_action = "wave" if idx == 0 else random.choice(["idle", "code", "walk"])
                vx = random.choice([-78.0, 78.0]) if init_action == "walk" else 0.0
                self.actors[pid] = Actor(
                    pet_id=pid,
                    x=px,
                    vx=vx,
                    facing=1 if vx >= 0 else -1,
                    action=init_action,
                    action_until=now + random.uniform(2.5, 5.5),
                    phase=random.uniform(0.0, 2.0),
                )

    def active_actors(self) -> List[Actor]:
        self._ensure_actors()
        out = [self.actors[pid] for pid in self.state.active_pets if pid in self.actors]
        if not out and self.actors:
            out = list(self.actors.values())
        return out

    def _personality(self, pid: str) -> dict:
        return PET_PERSONALITIES.get(pid, DEFAULT_PERSONALITY)

    def _save(self) -> None:
        self.known_mtime = self.state.save()
        self.last_save = time.time()

    def spawn(self, x: float, y: float, kind: str, rgb: Tuple[float, float, float], count: int = 4) -> None:
        for _ in range(count):
            ttl = random.uniform(1.0, 1.9)
            self.particles.append(
                Particle(
                    x=x + random.uniform(-34, 34),
                    y=y + random.uniform(-20, 14),
                    vx=random.uniform(-24, 24),
                    vy=random.uniform(-56, -26),
                    kind=kind,
                    size=random.uniform(7.0, 12.0),
                    ttl=ttl,
                    max_ttl=ttl,
                    rgb=rgb,
                )
            )

    def feed(self, already_applied: bool = False) -> None:
        now = time.time()
        leveled = False
        if not already_applied:
            self.state.hunger = min(100.0, self.state.hunger + 26.0)
            self.state.happiness = min(100.0, self.state.happiness + 8.0)
            self.state.energy = min(100.0, self.state.energy + 4.0)
            self.state.feeds_count += 1
            leveled = self.state.add_xp(12)
            self._save()
        self.ball_x = None
        actors = self.active_actors()
        speaker = random.choice(actors)
        for a in actors:
            a.action = "eat"
            a.vx = 0.0
            a.phase = 0.0
            a.action_until = now + 3.8
            if a is speaker:
                pers = self._personality(a.pet_id)
                a.speech = f"Level Up! Lv.{self.state.level}!" if leveled else random.choice(pers["feed"])
                a.speech_until = now + 3.5
            self.spawn(a.x, FLOOR_Y - a.height * 0.72, "star", (1.0, 0.85, 0.35), 4)

    def pat(self, target_id: Optional[str] = None, already_applied: bool = False) -> None:
        now = time.time()
        leveled = False
        if not already_applied:
            self.state.happiness = min(100.0, self.state.happiness + 15.0)
            self.state.pets_count += 1
            leveled = self.state.add_xp(10)
            self._save()
        targets = [self.actors[target_id]] if target_id in self.actors else self.active_actors()
        speaker = targets[0]
        for a in targets:
            a.action = "pet"
            a.vx = 0.0
            a.phase = 0.0
            a.action_until = now + 2.8
            pers = self._personality(a.pet_id)
            if a is speaker:
                a.speech = f"Level Up! Lv.{self.state.level}!" if leveled else random.choice(pers["pet"])
                a.speech_until = now + 3.2
            self.spawn(a.x, FLOOR_Y - a.height * 0.78, "heart", pers["glow"], 4)
            self.spawn(a.x, FLOOR_Y - a.height * 0.65, "star", (1.0, 0.88, 0.42), 2)

    def play(self, already_applied: bool = False) -> None:
        now = time.time()
        leveled = False
        if not already_applied:
            self.state.happiness = min(100.0, self.state.happiness + 20.0)
            self.state.energy = max(5.0, self.state.energy - 10.0)
            self.state.hunger = max(5.0, self.state.hunger - 5.0)
            leveled = self.state.add_xp(16)
            self._save()
        actors = self.active_actors()
        cx = sum(a.x for a in actors) / len(actors)
        self.ball_x = max(110.0, min(self.width - 110.0, cx + random.choice([-170.0, 170.0])))
        self.ball_y = FLOOR_Y - 72.0
        self.ball_vx = random.choice([-260.0, 260.0])
        self.ball_vy = -140.0
        speaker = random.choice(actors)
        for a in actors:
            a.action = "play"
            a.phase = 0.0
            a.action_until = now + 6.5
            if a is speaker:
                a.speech = f"Level Up! Lv.{self.state.level}!" if leveled else random.choice(PLAY_QUOTES)
                a.speech_until = now + 3.2
            self.spawn(a.x, FLOOR_Y - a.height * 0.62, "star", self._personality(a.pet_id)["glow"], 3)

    def toggle_sleep(self) -> None:
        now = time.time()
        actors = self.active_actors()
        if any(a.action == "sleep" for a in actors):
            for a in actors:
                a.action = "idle"
                a.phase = 0.0
                a.action_until = now + 3.2
            actors[0].speech = "hoaaam~ segar lagi!"
            actors[0].speech_until = now + 3.0
        else:
            self.ball_x = None
            for a in actors:
                a.action = "sleep"
                a.vx = 0.0
                a.phase = 0.0
                a.action_until = now + 999999.0
            actors[0].speech = "istirahat bentar... zZz"
            actors[0].speech_until = now + 3.0
        self._save()

    def toggle_pet_active(self, pid: str) -> None:
        if pid in self.state.active_pets:
            if len(self.state.active_pets) > 1:
                self.state.active_pets.remove(pid)
        elif pid in self.sprites.defs:
            self.state.active_pets.append(pid)
            self._ensure_actors()
            self.actors[pid].speech = "halo~ aku hadir!!"
            self.actors[pid].speech_until = time.time() + 2.8
        self._save()

    def show_all_pets(self) -> None:
        self.sprites.reload()
        self.state.active_pets = list(self.sprites.defs.keys())
        self._ensure_actors()
        self._save()

    def set_scope(self, scope: str) -> None:
        if scope in ("terminal", "always"):
            self.state.scope = scope
            self._save()

    def sync_external(self) -> None:
        now = time.time()
        if now - self.last_sync < 0.25:
            return
        self.last_sync = now
        try:
            mtime = STATE_FILE.stat().st_mtime
        except OSError:
            return
        if mtime <= self.known_mtime + 1e-6:
            return
        self.known_mtime = mtime
        self.sprites.reload()
        fresh = PetState.load(list(self.sprites.defs.keys()))
        self.state = fresh
        self._ensure_actors()
        if fresh.last_event_ts > self.known_event_ts:
            self.known_event_ts = fresh.last_event_ts
            ev = fresh.last_event
            if ev == "feed":
                self.feed(already_applied=True)
            elif ev == "pat":
                self.pat(already_applied=True)
            elif ev == "play":
                self.play(already_applied=True)
            elif ev == "sleep":
                self.toggle_sleep()

    def update(self, dt: float) -> None:
        now = time.time()
        self.sync_external()
        actors = self.active_actors()
        pad = 86.0
        min_x = pad
        max_x = max(pad + 140.0, self.width - pad)

        # Ambient sparkles
        if random.random() < dt * 1.6:
            a = random.choice(actors)
            if a.action != "sleep":
                glow = self._personality(a.pet_id)["glow"]
                self.particles.append(
                    Particle(
                        x=a.x + random.uniform(-a.width * 0.55, a.width * 0.55),
                        y=FLOOR_Y - random.uniform(22, a.height * 0.92),
                        vx=random.uniform(-6, 6),
                        vy=random.uniform(-18, -8),
                        kind="sparkle",
                        size=random.uniform(5.0, 9.0),
                        ttl=1.3,
                        max_ttl=1.3,
                        rgb=glow,
                    )
                )

        # Ball physics
        if self.ball_x is not None:
            self.ball_vy += 680.0 * dt
            self.ball_x += self.ball_vx * dt
            self.ball_y += self.ball_vy * dt
            self.ball_vx *= 0.992
            if self.ball_y >= FLOOR_Y - 12.0:
                self.ball_y = FLOOR_Y - 12.0
                self.ball_vy = -abs(self.ball_vy) * 0.72
                if abs(self.ball_vy) < 40.0:
                    self.ball_vy = -140.0
            if self.ball_x <= min_x:
                self.ball_x = min_x
                self.ball_vx = abs(self.ball_vx) * 0.85 + 60.0
            elif self.ball_x >= max_x:
                self.ball_x = max_x
                self.ball_vx = -abs(self.ball_vx) * 0.85 - 60.0
            if all(a.action != "play" for a in actors):
                self.ball_x = None

        for a in actors:
            a.phase += dt

            if a.action == "play" and self.ball_x is not None:
                diff = self.ball_x - a.x
                if abs(diff) > 28.0:
                    a.facing = 1 if diff > 0 else -1
                    a.x += math.copysign(min(abs(diff), 158.0 * dt), diff)
                elif random.random() < dt * 3.0:
                    self.ball_vx = random.choice([-270.0, 270.0])
                    self.ball_vy = -215.0
                    self.spawn(self.ball_x, self.ball_y, "star", self._personality(a.pet_id)["glow"], 3)
            elif a.action == "walk":
                a.x += a.vx * dt
                if a.x <= min_x:
                    a.x = min_x
                    a.vx = abs(a.vx)
                    a.facing = 1
                elif a.x >= max_x:
                    a.x = max_x
                    a.vx = -abs(a.vx)
                    a.facing = -1
            elif a.action == "sleep" and random.random() < dt * 0.9:
                self.particles.append(
                    Particle(
                        x=a.x + a.width * 0.25,
                        y=FLOOR_Y - a.height * 0.76,
                        vx=random.uniform(8, 18),
                        vy=-26.0,
                        kind="z",
                        size=random.uniform(11.0, 15.0),
                        ttl=1.7,
                        max_ttl=1.7,
                        rgb=(0.68, 0.78, 1.0),
                    )
                )

            a.x = max(min_x, min(max_x, a.x))

            if now >= a.action_until:
                a.phase = 0.0
                roll = random.random()
                if roll < 0.48:
                    direction = random.choice([-1, 1])
                    if a.x < min_x + 120:
                        direction = 1
                    elif a.x > max_x - 120:
                        direction = -1
                    a.action = "walk"
                    a.facing = direction
                    a.vx = direction * random.uniform(62.0, 102.0)
                    a.action_until = now + random.uniform(3.0, 6.2)
                elif roll < 0.74:
                    a.action = "code"
                    a.vx = 0.0
                    a.action_until = now + random.uniform(5.5, 10.0)
                    # Only one character speaks at a time so bubbles stay clean
                    if random.random() < 0.35 and all(now >= o.speech_until for o in actors):
                        a.speech = random.choice(self._personality(a.pet_id)["idle"])
                        a.speech_until = now + 3.5
                elif roll < 0.90:
                    a.action = random.choice(["idle", "wave", "stretch"])
                    a.vx = 0.0
                    a.action_until = now + random.uniform(3.0, 5.8)
                    if random.random() < 0.35 and all(now >= o.speech_until for o in actors):
                        a.speech = random.choice(self._personality(a.pet_id)["idle"])
                        a.speech_until = now + 3.5
                else:
                    a.action = "sleep"
                    a.vx = 0.0
                    a.action_until = now + random.uniform(8.0, 14.0)

        # Gentle spacing between idle/resting pets so all 4 stay clearly visible
        for i in range(len(actors)):
            for j in range(i + 1, len(actors)):
                a, b = actors[i], actors[j]
                if a.action in ("idle", "code", "eat", "wave", "sleep") and b.action in ("idle", "code", "eat", "wave", "sleep"):
                    dist = b.x - a.x
                    min_gap = 122.0
                    if abs(dist) < min_gap:
                        push = 48.0 * dt
                        if dist >= 0:
                            a.x = max(min_x, a.x - push)
                            b.x = min(max_x, b.x + push)
                        else:
                            b.x = max(min_x, b.x - push)
                            a.x = min(max_x, a.x + push)

        alive: List[Particle] = []
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.ttl -= dt
            if p.ttl > 0:
                alive.append(p)
        self.particles = alive

        if now - self.last_save > 45.0:
            self._save()


def draw_rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def draw_star(cr: cairo.Context, cx: float, cy: float, size: float, rgb: Tuple[float, float, float], alpha: float) -> None:
    cr.save()
    cr.translate(cx, cy)
    grad = cairo.RadialGradient(0, 0, 0, 0, 0, size * 1.45)
    grad.add_color_stop_rgba(0, rgb[0], rgb[1], rgb[2], alpha * 0.55)
    grad.add_color_stop_rgba(1, rgb[0], rgb[1], rgb[2], 0.0)
    cr.set_source(grad)
    cr.arc(0, 0, size * 1.45, 0, math.tau)
    cr.fill()

    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    inner = size * 0.24
    cr.move_to(0, -size)
    cr.line_to(inner, -inner)
    cr.line_to(size, 0)
    cr.line_to(inner, inner)
    cr.line_to(0, size)
    cr.line_to(-inner, inner)
    cr.line_to(-size, 0)
    cr.line_to(-inner, -inner)
    cr.close_path()
    cr.fill()
    cr.restore()


def draw_heart(cr: cairo.Context, cx: float, cy: float, size: float, rgb: Tuple[float, float, float], alpha: float) -> None:
    cr.save()
    cr.translate(cx, cy)
    s = size * 0.08
    cr.scale(s, s)
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    cr.move_to(0, 3)
    cr.curve_to(0, -1, -7, -6, -7, -1)
    cr.curve_to(-7, 4, 0, 8, 0, 11)
    cr.curve_to(0, 8, 7, 4, 7, -1)
    cr.curve_to(7, -6, 0, -1, 0, 3)
    cr.fill()
    cr.restore()


def draw_speech_bubble(
    cr: cairo.Context,
    cx: float,
    top_y: float,
    text: str,
    max_w: float,
    accent_rgb: Tuple[float, float, float],
) -> None:
    if not text:
        return
    cr.save()
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(12.5)
    ext = cr.text_extents(text)
    pad_x = 12.0
    bw = ext.width + pad_x * 2
    bh = 25.0
    bx = max(12.0, min(max_w - bw - 12.0, cx - bw * 0.5))
    by = max(4.0, top_y - bh - 8.0)

    draw_rounded_rect(cr, bx, by, bw, bh, 12.0)
    cr.set_source_rgba(0.08, 0.09, 0.17, 0.88)
    cr.fill_preserve()
    cr.set_source_rgba(accent_rgb[0], accent_rgb[1], accent_rgb[2], 0.58)
    cr.set_line_width(1.2)
    cr.stroke()

    cr.set_source_rgba(0.96, 0.97, 1.0, 0.98)
    cr.move_to(bx + pad_x - ext.x_bearing, by + (bh - ext.height) * 0.5 - ext.y_bearing)
    cr.show_text(text)
    cr.restore()


def render_world(
    cr: cairo.Context,
    world: SquadWorld,
    sprites: OpenPetSpriteBank,
    width: int,
    height: int,
    clear_transparent: bool = True,
) -> List[Tuple[int, int, int, int, str]]:
    if clear_transparent:
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.restore()

    now = time.time()
    hit_rects: List[Tuple[int, int, int, int, str]] = []

    for a in world.active_actors():
        surf = sprites.get_frame(a.pet_id, a.action, a.facing, a.phase)
        if surf is None:
            continue
        sw = surf.get_width()
        sh = surf.get_height()
        a.width = float(sw)
        a.height = float(sh)

        # Gentle floating bob for ghost + joyful hop on pet
        lift = 0.0
        if a.pet_id == "halloween-ghost" and a.action != "sleep":
            lift += 6.0 + math.sin(a.phase * 3.8) * 5.0
        if a.action == "pet":
            lift += abs(math.sin(a.phase * 8.0)) * 6.0
        alpha = 0.88 if a.action == "sleep" else 1.0
        glow = world._personality(a.pet_id)["glow"]

        # Soft floor shadow + signature colored glow
        cr.save()
        shadow_r = sw * 0.45 * (1.0 - min(0.32, lift / 70.0))
        grad = cairo.RadialGradient(a.x, FLOOR_Y + 3, 2, a.x, FLOOR_Y + 3, shadow_r)
        grad.add_color_stop_rgba(0.0, glow[0], glow[1], glow[2], 0.30)
        grad.add_color_stop_rgba(0.45, 0.06, 0.07, 0.16, 0.42)
        grad.add_color_stop_rgba(1.0, 0.04, 0.05, 0.10, 0.0)
        cr.set_source(grad)
        cr.save()
        cr.translate(a.x, FLOOR_Y + 3)
        cr.scale(1.18, 0.26)
        cr.arc(0, 0, shadow_r, 0, math.tau)
        cr.fill()
        cr.restore()

        # Glossy floor reflection beneath feet
        cr.save()
        cr.rectangle(a.x - sw, FLOOR_Y, sw * 2, 26)
        cr.clip()
        cr.translate(a.x, FLOOR_Y + lift * 0.25)
        cr.scale(1.0, -0.25)
        cr.set_source_surface(surf, -sw * 0.5, -sh)
        cr.paint_with_alpha(0.22 * alpha)
        cr.restore()
        cr.restore()

        # Main crisp anti-aliased OpenPets sprite frame
        cr.save()
        cr.translate(a.x, FLOOR_Y - lift)
        cr.set_source_surface(surf, -sw * 0.5, -sh)
        cr.paint_with_alpha(alpha)
        cr.restore()

        if now < a.speech_until and a.speech:
            draw_speech_bubble(cr, a.x, FLOOR_Y - sh - lift, a.speech, float(width), glow)

        rx = max(0, int(a.x - sw * 0.44))
        ry = max(0, int(FLOOR_Y - sh - lift - 8))
        rw = int(sw * 0.88)
        rh = int(sh + lift + 14)
        hit_rects.append((rx, ry, rw, rh, a.pet_id))

    if world.ball_x is not None:
        bx, by = world.ball_x, world.ball_y
        cr.save()
        bglow = cairo.RadialGradient(bx, by, 1, bx, by, 22)
        bglow.add_color_stop_rgba(0, 0.78, 0.42, 1.0, 0.90)
        bglow.add_color_stop_rgba(0.5, 0.45, 0.65, 1.0, 0.38)
        bglow.add_color_stop_rgba(1, 0.3, 0.3, 0.8, 0.0)
        cr.set_source(bglow)
        cr.arc(bx, by, 22, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(0.84, 0.58, 1.0, 1.0)
        cr.arc(bx, by, 8.5, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.88)
        cr.arc(bx - 2.5, by - 2.5, 2.5, 0, math.tau)
        cr.fill()
        cr.restore()
        hit_rects.append((int(bx - 16), int(by - 16), 32, 32, "ball"))

    for p in world.particles:
        alpha = max(0.0, min(1.0, p.ttl / p.max_ttl))
        if p.kind == "heart":
            draw_heart(cr, p.x, p.y, p.size, p.rgb, alpha)
        elif p.kind in ("star", "sparkle"):
            draw_star(cr, p.x, p.y, p.size, p.rgb, alpha)
        elif p.kind == "z":
            cr.save()
            cr.select_font_face("Sans", cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(p.size)
            cr.set_source_rgba(p.rgb[0], p.rgb[1], p.rgb[2], alpha)
            cr.move_to(p.x, p.y)
            cr.show_text("z")
            cr.restore()

    return hit_rects


class SquadOverlayWindow(Gtk.Window):
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
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        mon_w = 1920
        try:
            disp = Gdk.Display.get_default()
            if disp and disp.get_n_monitors() > 0:
                geo = disp.get_monitor(0).get_geometry()
                mon_w = max(800, geo.width)
        except Exception:
            pass
        self.win_w = min(1160, mon_w - 40)
        self.win_h = SURF_H
        self.set_default_size(self.win_w, self.win_h)
        self.set_size_request(self.win_w, self.win_h)

        lib = _load_layer_shell()
        if lib and lib.gtk_layer_is_supported():
            ptr = _gobject_ptr(self)
            lib.gtk_layer_init_for_window(ptr)
            lib.gtk_layer_set_namespace(ptr, b"cli-pet-overlay")
            lib.gtk_layer_set_layer(ptr, LAYER_TOP)
            lib.gtk_layer_set_anchor(ptr, EDGE_BOTTOM, True)
            lib.gtk_layer_set_margin(ptr, EDGE_BOTTOM, 6)
            lib.gtk_layer_set_exclusive_zone(ptr, 0)
            lib.gtk_layer_set_keyboard_mode(ptr, KB_NONE)

        self.focus_watcher = CosmicFocusWatcher()
        self.sprites = OpenPetSpriteBank()
        state = PetState.load(list(self.sprites.defs.keys()))
        self.world = SquadWorld(self.win_w, self.sprites, state)
        self.hit_rects: List[Tuple[int, int, int, int, str]] = []
        self.currently_visible: bool = False
        self.menu_open: bool = False
        self.last_tick = time.time()
        self._last_region_sig: Tuple[Tuple[int, int, int, int], ...] = ()
        self._frame_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.win_w, self.win_h)
        self._rgba_buf = np.zeros((self.win_h, self.win_w, 4), dtype=np.uint8)
        self._pixbuf_ref: Optional[bytes] = None

        self.img_widget = Gtk.Image()
        self.add(self.img_widget)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.on_click)
        self.connect("destroy", self._on_destroy)

        self.hide()
        GLib.timeout_add(42, self.on_tick)

    def _on_destroy(self, *_args) -> None:
        self.focus_watcher.stop()
        Gtk.main_quit()

    def _should_be_visible(self) -> bool:
        if HIDDEN_FILE.exists():
            return False
        if self.menu_open:
            return True
        if self.world.state.scope == "always":
            return True
        return self.focus_watcher.terminal_focused

    def _update_input_region(self) -> None:
        gdk_win = self.get_window()
        if gdk_win is None:
            return
        sig = tuple((x // 6, y // 6, w // 6, h // 6) for x, y, w, h, _ in self.hit_rects)
        if sig == self._last_region_sig:
            return
        self._last_region_sig = sig
        reg = _libcairo.cairo_region_create()
        for x, y, w, h, _ in self.hit_rects:
            rect = _CairoRectInt(x, y, max(1, w), max(1, h))
            _libcairo.cairo_region_union_rectangle(reg, ctypes.byref(rect))
        _libgdk.gdk_window_input_shape_combine_region(_gobject_ptr(gdk_win), reg, 0, 0)
        _libcairo.cairo_region_destroy(reg)

    def _render_frame(self) -> None:
        cr = cairo.Context(self._frame_surf)
        self.hit_rects = render_world(cr, self.world, self.sprites, self.win_w, self.win_h, True)
        pb, raw = cairo_surface_to_pixbuf(self._frame_surf, self._rgba_buf)
        self._pixbuf_ref = raw
        self.img_widget.set_from_pixbuf(pb)
        self._update_input_region()

    def on_tick(self) -> bool:
        now = time.time()
        dt = min(0.1, max(0.005, now - self.last_tick))
        self.last_tick = now

        self.world.sync_external()

        want_vis = self._should_be_visible()
        if want_vis != self.currently_visible:
            self.currently_visible = want_vis
            if want_vis:
                self._last_region_sig = ()
                self.show_all()
                self._render_frame()
            else:
                self.hide()

        if self.currently_visible:
            self.world.update(dt)
            self._render_frame()
        return True

    def on_click(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        clicked_id: Optional[str] = None
        for x, y, w, h, pid in self.hit_rects:
            if x <= event.x <= x + w and y <= event.y <= y + h:
                clicked_id = pid
                break

        if event.button == 1:
            if event.type == Gdk.EventType._2BUTTON_PRESS:
                self.world.play()
            else:
                target = clicked_id if clicked_id in self.sprites.defs else None
                self.world.pat(target_id=target)
            return True

        if event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        self.menu_open = True
        menu = Gtk.Menu()
        menu.connect("deactivate", lambda _m: setattr(self, "menu_open", False))

        def add_item(label: str, cb) -> None:
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", cb)
            menu.append(mi)

        add_item("Kasih Makan Semua (Feed)", lambda _w: self.world.feed())
        add_item("Sapa / Elus Semua (Pat)", lambda _w: self.world.pat())
        add_item("Main Bola (Play)", lambda _w: self.world.play())
        add_item("Tidur / Bangun", lambda _w: self.world.toggle_sleep())
        menu.append(Gtk.SeparatorMenuItem())

        add_item("Tampilkan Semua Pet", lambda _w: self.world.show_all_pets())
        for pid, pdef in self.sprites.defs.items():
            mark = "✓" if pid in self.world.state.active_pets else "  "
            add_item(f"[{mark}] {pdef.display_name}", lambda _w, p=pid: self.world.toggle_pet_active(p))

        menu.append(Gtk.SeparatorMenuItem())
        is_term = self.world.state.scope == "terminal"
        next_scope = "always" if is_term else "terminal"
        add_item(
            "Ubah ke: Semua Layar" if is_term else "Ubah ke: Hanya di Terminal",
            lambda _w: self.world.set_scope(next_scope),
        )
        add_item("Sembunyikan (pet show untuk munculkan)", lambda _w: self._hide_self())
        menu.show_all()
        menu.popup_at_pointer(event)

    def _hide_self(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        HIDDEN_FILE.write_text("1\n", encoding="utf-8")
        self.currently_visible = False
        self.hide()


def render_preview_png(out_path: str) -> None:
    w, h = 1120, SURF_H + 28
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)

    bg = cairo.LinearGradient(0, 0, 0, h)
    bg.add_color_stop_rgba(0, 0.05, 0.06, 0.11, 1.0)
    bg.add_color_stop_rgba(0.82, 0.08, 0.10, 0.18, 1.0)
    bg.add_color_stop_rgba(1.0, 0.04, 0.05, 0.10, 1.0)
    cr.set_source(bg)
    cr.paint()

    sprites = OpenPetSpriteBank()
    all_ids = list(sprites.defs.keys())
    state = PetState(active_pets=all_ids)
    world = SquadWorld(w, sprites, state)
    # Pose each pet nicely for the squad preview
    positions = [170, 420, 690, 945]
    poses = ["code", "idle", "wave", "code"]
    for idx, pid in enumerate(all_ids[:4]):
        a = world.actors[pid]
        a.x = float(positions[idx])
        a.action = poses[idx]
        a.phase = 0.25
        if idx == 0:
            a.speech = "Domain Expansion: No Bugs!"
            a.speech_until = time.time() + 10
        elif idx == 2:
            a.speech = "booo~ aku hantu ramah!"
            a.speech_until = time.time() + 10

    world.particles = [
        Particle(245, 76, 0, 0, "sparkle", 10, 1, 1, (0.72, 0.54, 1.0)),
        Particle(755, 86, 0, 0, "sparkle", 9, 1, 1, (0.52, 0.88, 1.0)),
        Particle(1015, 84, 0, 0, "sparkle", 9, 1, 1, (1.0, 0.82, 0.36)),
    ]

    cr.save()
    cr.translate(0, 20)
    render_world(cr, world, sprites, w, SURF_H, clear_transparent=False)
    cr.restore()

    surf.write_to_png(out_path)
    print(f"Saved squad preview ({len(all_ids)} pets: {all_ids}) to {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="cli-pet OpenPets HD Terminal Overlay")
    parser.add_argument("--preview", type=str, help="Render squad preview PNG and exit")
    args = parser.parse_args()

    if args.preview:
        render_preview_png(args.preview)
        return 0

    os.environ.setdefault("GDK_BACKEND", "wayland")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())

    SquadOverlayWindow()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
