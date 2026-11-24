# Hollow Suite (Pop!_OS COSMIC + Modern Zsh CLI)

Paket kustomisasi lengkap bertema **Hollow Purple** yang terpasang di sistem kamu:

## 1. Terminal Modern (`~/.zshrc`)
- **`fastfetch`** — menggantikan `neofetch` saat buka terminal (tema Hollow Purple, 20x lebih cepat)
- **`ls` / `ll` / `la` / `lt`** → **`eza`** (ikon file + status git + tree view)
- **`cat` / `catp`** → **`bat`** (syntax highlighting tema Dracula + nomor baris)
- **`z <folder>`** → **`zoxide`** (loncat cepat ke folder yang pernah dikunjungi)
- **`Ctrl+R`** & **`Ctrl+T`** → **`fzf`** (cari history command & file dengan live preview `bat`, tema ungu-biru)
- **`rg`** (ripgrep) & **`fd`** (pencarian cepat)
- **`top`** / **`btop`** → monitor CPU/RAM/network tema `tokyo-night` transparan
- **`lg`** / **`lazygit`** → Git TUI visual tema Hollow Purple

## 2. Live Neon Audio Visualizer (`hollow-visualizer.service`)
- Otomatis menyala di tepi bawah desktop setiap kali ada audio/musik (Spotify, YouTube, dll.), dan otomatis sembunyi (0% visual) saat hening.
- Perintah: `viz status`, `viz mode bars`, `viz mode wave`, `viz start`, `viz stop`

## 3. Glassmorphism Clipboard & Quick Dev Panel (`hollow-clipboard.service`)
- **`Super+V`** atau ketik `clip` → buka **Riwayat Clipboard** (40 copy terakhir, bisa cari langsung, klik/Enter untuk salin ulang)
- **`Super+Shift+D`** atau ketik `dev` → buka **Dev Panel** (toggle 1-klik PostgreSQL, MySQL, Mode Fokus / Hemat Baterai, Audio Visualizer, daftar Port Lokal Aktif, & shortcut `btop`/`lazygit`)
