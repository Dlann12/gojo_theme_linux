#!/usr/bin/env bash
# Restore Gojo Hollow Purple Pop!_OS COSMIC Rice & Modern CLI Suite for any Linux user
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "✦ Memulihkan tema & konfigurasi Gojo Hollow Purple untuk user: $USER ($HOME)"

# 1. Backup existing dotfiles safely before overwriting
TS="$(date +%Y%m%d-%H%M%S)"
for f in .zshrc .p10k.zsh; do
  if [[ -f "$HOME/$f" ]]; then
    cp -a "$HOME/$f" "$HOME/${f}.bak-${TS}"
  fi
done

# 2. Copy dotfiles (skip overwriting user's git identity; only copy .zshrc & .p10k.zsh)
cp -a "$DIR/home/.zshrc" "$HOME/.zshrc"
[[ -f "$DIR/home/.p10k.zsh" ]] && cp -a "$DIR/home/.p10k.zsh" "$HOME/.p10k.zsh"

# 3. Copy configs, systemd services, scripts, and projects
mkdir -p "$HOME/.config/cosmic" "$HOME/.config/systemd/user" "$HOME/.local/bin" "$HOME/.local/share/hollow-suite"
cp -a "$DIR/config/." "$HOME/.config/"
cp -a "$DIR/systemd/." "$HOME/.config/systemd/user/"
cp -a "$DIR/local-bin/." "$HOME/.local/bin/"

INSTALL_BASE="$HOME/.local/share/hollow-suite"
cp -a "$DIR/projects/." "$INSTALL_BASE/"

# 4. Make paths portable for any username ($HOME instead of /home/kerja)
for target in \
  "$HOME/.zshrc" \
  "$HOME/.config/cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom" \
  "$INSTALL_BASE/hollow-suite/hollow_panel.py" \
  "$INSTALL_BASE/hollow-suite/backup-rice"; do
  if [[ -f "$target" ]]; then
    sed -i "s|/home/kerja/.gemini/antigravity/scratch|$INSTALL_BASE|g" "$target"
    sed -i "s|/home/kerja|$HOME|g" "$target"
  fi
done

# 5. Create executable symlinks in ~/.local/bin
chmod +x "$INSTALL_BASE/cli-pet/pet.py" \
         "$INSTALL_BASE/cli-pet/pet_overlay.py" \
         "$INSTALL_BASE/hollow-suite/hollow_visualizer.py" \
         "$INSTALL_BASE/hollow-suite/clipboard_daemon.py" \
         "$INSTALL_BASE/hollow-suite/hollow_panel.py" \
         "$INSTALL_BASE/hollow-suite/hollow_osd.py" \
         "$INSTALL_BASE/hollow-suite/hollow_notify.py" \
         "$INSTALL_BASE/hollow-suite/hollow_clock.py" \
         "$INSTALL_BASE/hollow-suite/backup-rice"

ln -sf "$INSTALL_BASE/cli-pet/pet.py" "$HOME/.local/bin/pet"
ln -sf "$INSTALL_BASE/cli-pet/pet_overlay.py" "$HOME/.local/bin/pet-overlay"
ln -sf "$INSTALL_BASE/hollow-suite/hollow_visualizer.py" "$HOME/.local/bin/hollow-viz"
ln -sf "$INSTALL_BASE/hollow-suite/clipboard_daemon.py" "$HOME/.local/bin/hollow-clipboard"
ln -sf "$INSTALL_BASE/hollow-suite/hollow_panel.py" "$HOME/.local/bin/dev-panel"
ln -sf "$INSTALL_BASE/hollow-suite/hollow_panel.py" "$HOME/.local/bin/clip-panel"
ln -sf "$INSTALL_BASE/hollow-suite/hollow_osd.py" "$HOME/.local/bin/hollow-osd"
ln -sf "$INSTALL_BASE/hollow-suite/hollow_notify.py" "$HOME/.local/bin/hollow-notify"
ln -sf "$INSTALL_BASE/hollow-suite/hollow_clock.py" "$HOME/.local/bin/hollow-clock"
ln -sf "$INSTALL_BASE/hollow-suite/backup-rice" "$HOME/.local/bin/backup-rice"
[[ -x /usr/bin/fdfind ]] && ln -sf /usr/bin/fdfind "$HOME/.local/bin/fd"

# 6. Enable & start Hollow Suite + Pet background services
systemctl --user daemon-reload
systemctl --user enable --now \
  cli-pet.service \
  hollow-visualizer.service \
  hollow-clipboard.service \
  hollow-osd.service 2>/dev/null || true

echo ""
echo "✓ Instalasi konfigurasi selesai!"
echo "  - Buka jendela cosmic-term baru untuk melihat tema Hollow Purple & pet 3D."
echo "  - Jika ingin memakai git delta, jalankan: git config --global core.pager delta && git config --global delta.side-by-side true"
echo "  - Startpage browser lokal: file://$INSTALL_BASE/hollow-suite/startpage/index.html"
