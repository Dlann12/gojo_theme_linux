#!/usr/bin/env python3
"""
hollow-notify: Native D-Bus desktop notification + gentle completion sound
for long-running terminal commands (no notify-send dependency required).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

SOUND_OK = Path("/usr/share/sounds/freedesktop/stereo/complete.oga")
SOUND_ERR = Path("/usr/share/sounds/freedesktop/stereo/bell.oga")


def send_notification(title: str, body: str, is_error: bool = False) -> None:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        icon = "dialog-error" if is_error else "utilities-terminal"
        bus.call_sync(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
            GLib.Variant(
                "(susssasa{sv}i)",
                ("Hollow Terminal", 0, icon, title, body, [], {}, 5000),
            ),
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
    except Exception:
        pass

    snd = SOUND_ERR if is_error else SOUND_OK
    if snd.exists():
        try:
            subprocess.Popen(
                ["paplay", str(snd)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else "Terminal Selesai"
    body = sys.argv[2] if len(sys.argv) > 2 else ""
    is_err = (len(sys.argv) > 3 and sys.argv[3] != "0")
    send_notification(title, body, is_err)
