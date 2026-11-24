#!/usr/bin/env python3
"""
hollow-clipboard: Lightweight Wayland clipboard history daemon using native GTK3 signals.
Zero polling; records the last 40 copied text snippets to ~/.local/share/hollow-suite/clipboard.json.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import List

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

DATA_DIR = Path.home() / ".local" / "share" / "hollow-suite"
CLIP_FILE = DATA_DIR / "clipboard.json"
MAX_ITEMS = 40
MAX_LEN = 4096


def load_history() -> List[dict]:
    if CLIP_FILE.exists():
        try:
            data = json.loads(CLIP_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return []


def save_history(items: List[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CLIP_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[:MAX_ITEMS], indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CLIP_FILE)


class ClipboardDaemon:
    def __init__(self) -> None:
        self.history = load_history()
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard.connect("owner-change", self.on_owner_change)

    def on_owner_change(self, _cb: Gtk.Clipboard, _event) -> None:
        self.clipboard.request_text(self.on_text_received)

    def on_text_received(self, _cb: Gtk.Clipboard, text: str | None) -> None:
        if not text:
            return
        cleaned = text.strip()
        if not cleaned:
            return
        snippet = text[:MAX_LEN]
        # Reload in case panel cleared history
        self.history = load_history()
        self.history = [item for item in self.history if item.get("text") != snippet]
        self.history.insert(0, {"text": snippet, "ts": time.time()})
        self.history = self.history[:MAX_ITEMS]
        save_history(self.history)


def main() -> int:
    os.environ.setdefault("GDK_BACKEND", "wayland")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    ClipboardDaemon()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
