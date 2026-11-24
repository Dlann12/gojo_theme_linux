#!/usr/bin/env python3
"""
pet: Fast CLI controller for the OpenPets HD Terminal Overlay.
Supports Gojo + any pet installed via `npx -y install-pet <slug>`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent
LOCAL_ASSETS_DIR = BASE_DIR / "assets"
OPENPETS_DIR = Path.home() / ".config" / "OpenPets" / "pets"
STATE_DIR = Path.home() / ".config" / "cli-pet"
STATE_FILE = STATE_DIR / "state.json"
HIDDEN_FILE = STATE_DIR / "hidden"
SERVICE_NAME = "cli-pet.service"
OVERLAY_BIN = Path.home() / ".local" / "bin" / "pet-overlay"


def discover_pets() -> Dict[str, str]:
    found: Dict[str, str] = {}
    dirs: List[Path] = []
    if LOCAL_ASSETS_DIR.exists():
        dirs.extend(sorted(p for p in LOCAL_ASSETS_DIR.iterdir() if p.is_dir()))
    if OPENPETS_DIR.exists():
        dirs.extend(sorted(p for p in OPENPETS_DIR.iterdir() if p.is_dir()))
    for d in dirs:
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
            found[pid] = name
    return found


def resolve_pet_id(query: str, available: Dict[str, str]) -> str | None:
    q = query.lower().strip()
    if q in available:
        return q
    for pid, name in available.items():
        if q in pid.lower() or q in name.lower():
            return pid
    return None


def load_state(available: Dict[str, str]) -> dict:
    all_ids = list(available.keys())
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            raw = st.get("active_pets")
            if isinstance(raw, list):
                st["active_pets"] = [p for p in raw if p in available] or all_ids
            else:
                st["active_pets"] = all_ids
            return st
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "active_pets": all_ids,
        "scope": "terminal",
        "hunger": 85.0,
        "happiness": 88.0,
        "energy": 90.0,
        "xp": 0,
        "level": 1,
        "pets_count": 0,
        "feeds_count": 0,
        "born_ts": time.time(),
        "last_ts": time.time(),
        "last_event": "",
        "last_event_ts": 0.0,
    }


def save_state(st: dict) -> None:
    st["last_ts"] = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def add_xp(st: dict, amount: int) -> bool:
    st["xp"] = int(st.get("xp", 0)) + amount
    lvl = max(1, int(st.get("level", 1)))
    leveled = False
    while st["xp"] >= lvl * 50:
        st["xp"] -= lvl * 50
        lvl += 1
        leveled = True
    st["level"] = lvl
    return leveled


def ensure_overlay_running() -> None:
    if HIDDEN_FILE.exists():
        try:
            HIDDEN_FILE.unlink()
        except OSError:
            pass
    res = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME], check=False)
    if res.returncode != 0:
        r2 = subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], check=False)
        if r2.returncode != 0 and OVERLAY_BIN.exists():
            subprocess.Popen(
                [str(OVERLAY_BIN)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )


def make_bar(val: float, w: int = 10) -> str:
    n = int(round(max(0.0, min(100.0, val)) / 100.0 * w))
    return "█" * n + "░" * (w - n)


def print_status(st: dict, available: Dict[str, str], note: str = "") -> None:
    active_names = [available.get(p, p) for p in st.get("active_pets", [])]
    scope = "Hanya di Terminal" if st.get("scope", "terminal") == "terminal" else "Semua Layar"
    vis = "Tersembunyi" if HIDDEN_FILE.exists() else scope
    print(f"✦ Aktif ({len(active_names)}): {', '.join(active_names)} · Lv.{st.get('level', 1)} [{vis}]")
    print(f"  Kenyang : {make_bar(float(st.get('hunger', 85)))} {int(st.get('hunger', 85))}%")
    print(f"  Senang  : {make_bar(float(st.get('happiness', 88)))} {int(st.get('happiness', 88))}%")
    print(f"  Energi  : {make_bar(float(st.get('energy', 90)))} {int(st.get('energy', 90))}%")
    if note:
        print(f"  → {note}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pet",
        description="Kontroler CLI untuk overlay OpenPets 3D di terminal.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=[
            "show", "hide", "feed", "pat", "play", "sleep",
            "list", "all", "only", "add", "remove", "reload",
            "scope", "status", "autostart",
        ],
        default="show",
    )
    parser.add_argument("value", nargs="?", help="ID/nama pet, terminal|always, atau on|off")
    args = parser.parse_args()

    if args.command == "autostart":
        if args.value == "off":
            subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], check=False)
            print("Auto-start pet overlay: NONAKTIF.")
        elif args.value == "on":
            if HIDDEN_FILE.exists():
                HIDDEN_FILE.unlink()
            subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=False)
            print("Auto-start pet overlay: AKTIF (langsung muncul saat buka terminal).")
        else:
            en = subprocess.run(["systemctl", "--user", "is-enabled", "--quiet", SERVICE_NAME], check=False).returncode == 0
            act = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE_NAME], check=False).returncode == 0
            print(f"Auto-start: {'AKTIF' if en else 'NONAKTIF'} | Status: {'BERJALAN' if act else 'BERHENTI'}")
        return 0

    available = discover_pets()
    st = load_state(available)

    if args.command == "list":
        print("Daftar pet terpasang:")
        for pid, name in available.items():
            mark = "✓" if pid in st["active_pets"] else " "
            print(f"  [{mark}] {name} ({pid})")
        return 0

    if args.command == "hide":
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        HIDDEN_FILE.write_text("1\n", encoding="utf-8")
        print("Pet disembunyikan. Ketik `pet show` untuk memunculkan lagi.")
        return 0

    if args.command == "status":
        print_status(st, available)
        return 0

    ensure_overlay_running()

    if args.command == "show":
        print_status(st, available, "Aktif di terminal (klik kiri = elus, double-click = main bola, klik kanan = menu).")
        return 0

    if args.command == "all" or args.command == "reload":
        st["active_pets"] = list(available.keys())
        st["last_event"] = "reload"
        st["last_event_ts"] = time.time()
        save_state(st)
        print_status(st, available, "Semua pet ditampilkan!")
        return 0

    if args.command in ("only", "add", "remove"):
        if not args.value:
            print(f"Gunakan: pet {args.command} <nama/id>  (lihat daftar dengan `pet list`)")
            return 1
        pid = resolve_pet_id(args.value, available)
        if not pid:
            print(f"Pet '{args.value}' tidak ditemukan. Daftar: {', '.join(available.keys())}")
            return 1
        if args.command == "only":
            st["active_pets"] = [pid]
        elif args.command == "add":
            if pid not in st["active_pets"]:
                st["active_pets"].append(pid)
        elif args.command == "remove":
            if pid in st["active_pets"] and len(st["active_pets"]) > 1:
                st["active_pets"].remove(pid)
        st["last_event"] = "reload"
        st["last_event_ts"] = time.time()
        save_state(st)
        print_status(st, available)
        return 0

    if args.command == "feed":
        st["hunger"] = min(100.0, float(st.get("hunger", 85)) + 26.0)
        st["happiness"] = min(100.0, float(st.get("happiness", 88)) + 8.0)
        st["energy"] = min(100.0, float(st.get("energy", 90)) + 4.0)
        st["feeds_count"] = int(st.get("feeds_count", 0)) + 1
        lvl_up = add_xp(st, 12)
        st["last_event"] = "feed"
        st["last_event_ts"] = time.time()
        save_state(st)
        print_status(st, available, f"Level Up! Lv.{st['level']} ✦" if lvl_up else "Camilan diberikan ke semua pet! ♥")
        return 0

    if args.command == "pat":
        st["happiness"] = min(100.0, float(st.get("happiness", 88)) + 15.0)
        st["pets_count"] = int(st.get("pets_count", 0)) + 1
        lvl_up = add_xp(st, 10)
        st["last_event"] = "pat"
        st["last_event_ts"] = time.time()
        save_state(st)
        print_status(st, available, f"Level Up! Lv.{st['level']} ✦" if lvl_up else "Semua pet senang dielus! ♥")
        return 0

    if args.command == "play":
        st["happiness"] = min(100.0, float(st.get("happiness", 88)) + 20.0)
        st["energy"] = max(5.0, float(st.get("energy", 90)) - 10.0)
        st["hunger"] = max(5.0, float(st.get("hunger", 85)) - 5.0)
        lvl_up = add_xp(st, 16)
        st["last_event"] = "play"
        st["last_event_ts"] = time.time()
        save_state(st)
        print_status(st, available, f"Level Up! Lv.{st['level']} ✦" if lvl_up else "Orb dilempar! Semua pet sedang mengejar ✦")
        return 0

    if args.command == "sleep":
        st["last_event"] = "sleep"
        st["last_event_ts"] = time.time()
        save_state(st)
        print_status(st, available, "Toggle tidur / bangun dikirim.")
        return 0

    if args.command == "scope":
        if args.value not in ("terminal", "always"):
            print("Gunakan: pet scope <terminal|always>")
            return 1
        st["scope"] = args.value
        st["last_event"] = "scope"
        st["last_event_ts"] = time.time()
        save_state(st)
        lbl = "Hanya saat terminal fokus" if args.value == "terminal" else "Semua layar"
        print_status(st, available, f"Mode tampil diubah ke: {lbl}.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
