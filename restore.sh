#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Memulihkan dotfiles & konfigurasi Hollow Purple..."
cp -a "$DIR/home/." "$HOME/" 2>/dev/null || true
mkdir -p "$HOME/.config/cosmic" "$HOME/.config/systemd/user" "$HOME/.local/bin"
cp -a "$DIR/config/." "$HOME/.config/" 2>/dev/null || true
cp -a "$DIR/systemd/." "$HOME/.config/systemd/user/" 2>/dev/null || true
cp -a "$DIR/local-bin/." "$HOME/.local/bin/" 2>/dev/null || true

mkdir -p "$HOME/.gemini/antigravity/scratch"
cp -a "$DIR/projects/." "$HOME/.gemini/antigravity/scratch/" 2>/dev/null || true

ln -sf "$HOME/.gemini/antigravity/scratch/cli-pet/pet.py" "$HOME/.local/bin/pet"
ln -sf "$HOME/.gemini/antigravity/scratch/cli-pet/pet_overlay.py" "$HOME/.local/bin/pet-overlay"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/hollow_visualizer.py" "$HOME/.local/bin/hollow-viz"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/clipboard_daemon.py" "$HOME/.local/bin/hollow-clipboard"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/hollow_panel.py" "$HOME/.local/bin/dev-panel"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/hollow_panel.py" "$HOME/.local/bin/clip-panel"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/hollow_osd.py" "$HOME/.local/bin/hollow-osd"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/hollow_notify.py" "$HOME/.local/bin/hollow-notify"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/hollow_clock.py" "$HOME/.local/bin/hollow-clock"
ln -sf "$HOME/.gemini/antigravity/scratch/hollow-suite/backup-rice" "$HOME/.local/bin/backup-rice"

systemctl --user daemon-reload
systemctl --user enable --now cli-pet.service hollow-visualizer.service hollow-clipboard.service hollow-osd.service 2>/dev/null || true
echo "✓ Pemulihan selesai! Buka terminal baru untuk melihat hasilnya."
