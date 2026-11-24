#!/usr/bin/env python3
"""
hollow-clock: Hollow Purple 24-bit TrueColor Digital Clock & Starfield Terminal Screensaver.
Run via `idle` or `jam`. Press any key (q / Esc / Ctrl+C) to return cleanly to shell.
"""

from __future__ import annotations

import datetime
import math
import os
import random
import select
import shutil
import sys
import termios
import time
import tty
from typing import List, Tuple

DIGITS = {
    "0": ["█████", "█   █", "█   █", "█   █", "█████"],
    "1": ["  ██ ", " ███ ", "  ██ ", "  ██ ", "█████"],
    "2": ["█████", "    █", "█████", "█    ", "█████"],
    "3": ["█████", "    █", " ████", "    █", "█████"],
    "4": ["█   █", "█   █", "█████", "    █", "    █"],
    "5": ["█████", "█    ", "█████", "    █", "█████"],
    "6": ["█████", "█    ", "█████", "█   █", "█████"],
    "7": ["█████", "    █", "   █ ", "  █  ", "  █  "],
    "8": ["█████", "█   █", "█████", "█   █", "█████"],
    "9": ["█████", "█   █", "█████", "    █", "█████"],
    ":": ["     ", "  █  ", "     ", "  █  ", "     "],
}

DAYS_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MONTHS_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def lerp_rgb(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def read_mem_str() -> str:
    try:
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
        tot = info.get("MemTotal", 1)
        avail = info.get("MemAvailable", 0)
        used = tot - avail
        return f"RAM {used / 1048576:.1f}/{tot / 1048576:.1f} GiB"
    except OSError:
        return ""


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(datetime.datetime.now().strftime("%H:%M:%S"))
        return 0

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    stars: List[List[float]] = []
    last_dims = (0, 0)

    try:
        tty.setcbreak(fd)
        sys.stdout.buffer.write(b"\033[?1049h\033[?25l")
        sys.stdout.buffer.flush()

        t = 0.0
        while True:
            r, _, _ = select.select([fd], [], [], 0.08)
            if r:
                os.read(fd, 64)
                break

            t += 0.08
            ts = shutil.get_terminal_size((80, 24))
            cols, rows = max(36, ts.columns), max(12, ts.lines)

            if (cols, rows) != last_dims:
                last_dims = (cols, rows)
                stars = [
                    [
                        random.uniform(0, cols - 1),
                        random.uniform(0, rows - 1),
                        random.uniform(0.0, math.tau),
                        random.uniform(1.2, 3.2),
                    ]
                    for _ in range(max(18, (cols * rows) // 85))
                ]

            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M:%S")
            date_str = f"{DAYS_ID[now.weekday()]}, {now.day} {MONTHS_ID[now.month - 1]} {now.year}"
            mem_str = read_mem_str()

            # Build big 5-row clock lines
            clock_lines = [""] * 5
            for idx, ch in enumerate(time_str):
                glyph = DIGITS.get(ch, DIGITS[":"])
                sep = "  " if idx > 0 else ""
                for row_i in range(5):
                    clock_lines[row_i] += sep + glyph[row_i]

            cw = len(clock_lines[0])
            start_x = max(0, (cols - cw) // 2)
            start_y = max(2, (rows - 9) // 2)

            out = ["\033[?2026h\033[2J"]

            # Draw gentle twinkling Hollow Purple starfield
            for s in stars:
                sx, sy, ph, spd = s
                s[1] = (sy - 0.05) % max(1, rows - 1)
                twinkle = (math.sin(t * spd + ph) + 1.0) * 0.5
                ix, iy = int(sx), int(s[1])
                # Skip inside clock center box
                if start_y - 1 <= iy <= start_y + 7 and start_x - 3 <= ix <= start_x + cw + 3:
                    continue
                if twinkle > 0.72:
                    ch_s, rgb = "✦", (192, 132, 252) if ph < math.pi else (56, 189, 248)
                elif twinkle > 0.35:
                    ch_s, rgb = "·", (110, 95, 165)
                else:
                    continue
                out.append(f"\033[{iy + 1};{ix + 1}H\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{ch_s}")

            # Draw big gradient clock (Deep Purple -> Orchid -> Electric Cyan)
            for row_i, line in enumerate(clock_lines):
                y = start_y + row_i + 1
                out.append(f"\033[{y};{start_x + 1}H")
                for col_i, ch in enumerate(line):
                    if ch == " ":
                        out.append(" ")
                    else:
                        frac = (col_i / max(1, cw - 1))
                        # Subtle shimmer wave across digits
                        shimmer = (math.sin(t * 1.8 - frac * 4.0) + 1.0) * 0.12
                        f2 = min(1.0, frac + shimmer)
                        if f2 < 0.5:
                            rgb = lerp_rgb((124, 58, 237), (192, 132, 252), f2 * 2.0)
                        else:
                            rgb = lerp_rgb((192, 132, 252), (56, 189, 248), (f2 - 0.5) * 2.0)
                        out.append(f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m█")

            # Centered date & subtle divider
            dx = max(1, (cols - len(date_str)) // 2 + 1)
            out.append(f"\033[{start_y + 7};{dx}H\033[38;2;196;181;253m{date_str}")

            footer = f"Hollow Purple  ·  {mem_str}  ·  Tekan tombol apa saja untuk keluar"
            fx = max(1, (cols - len(footer)) // 2 + 1)
            out.append(f"\033[{rows};{fx}H\033[38;2;100;116;139m{footer[:cols - 1]}")
            out.append("\033[0m\033[?2026l")

            os.write(sys.stdout.fileno(), "".join(out).encode("utf-8"))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.buffer.write(b"\033[?25h\033[0m\033[?1049l")
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
