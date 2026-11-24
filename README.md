# Gojo Hollow Purple — Pop!_OS COSMIC Rice & Modern CLI Dotfiles

Full **Gojo Hollow Purple** desktop & terminal customization suite for **Pop!_OS COSMIC (Wayland)**.

## Included

### Desktop & Wayland Layer-Shell Overlays
- **COSMIC Dark Theme & Translucent `cosmic-term`** (`config/cosmic/`) — Hollow Purple palette (`#0d0e1a`, `#c084fc`, `#38bdf8`) with 86% glass opacity
- **HD Terminal Pet Overlay (`cli-pet`)** — 3D animated Gojo + OpenPets auto-discovery (`~/.config/OpenPets/pets/`), visible only when a terminal is focused (0% CPU otherwise)
- **Live Neon Audio Visualizer (`hollow-viz`)** — Real-time 36-band PipeWire/PulseAudio FFT neon bars & wave overlay at the bottom of the desktop
- **Volume & Brightness Glass HUD (`hollow-osd`)** — Wayland Layer-Shell floating neon pill triggered by hardware keys
- **Glassmorphism Clipboard Manager (`Super+V`) & Quick Dev Panel (`Super+Shift+D`)** — Searchable clipboard history + 1-click PostgreSQL/MySQL/Focus-Mode toggles & active local ports
- **Gojo Bento Desktop Widget, Power Menu & Custom Lockscreen** (`local-bin/`)
- **Local Hollow Purple Browser Startpage** (`projects/hollow-suite/startpage/index.html`)

### Modern Zsh CLI Suite
- `fastfetch` (Hollow Purple theme), `eza`, `bat`, `zoxide`, `fzf`, `ripgrep`, `fd`, `btop`, `lazygit`, `delta` (side-by-side diffs), `yazi` (3-pane file manager), `tldr`, and zero-dependency Hollow Purple **Neovim** (`config/nvim/init.lua`)
- **Long-running command desktop notifications** (`>= 15s`) + **`idle` / `jam`** TrueColor terminal clock screensaver

## Quick Restore
```bash
git clone https://github.com/Dlann12/gojo_theme_linux.git ~/rice-backup
cd ~/rice-backup
./restore.sh
```
