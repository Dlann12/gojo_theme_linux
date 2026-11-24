# Gojo Hollow Purple — Pop!_OS COSMIC Rice & Modern CLI Suite

Kustomisasi lengkap bertema **Gojo Hollow Purple** untuk **Pop!_OS COSMIC (Wayland)** + **Zsh Modern CLI**.

---

## Fitur Utama

### Desktop & Wayland Layer-Shell Overlays
- **COSMIC Dark Theme & `cosmic-term` Glass** (`config/cosmic/`) — palet *Hollow Purple* (`#0d0e1a`, `#c084fc`, `#38bdf8`) dengan transparansi 86%.
- **3D Terminal Pet Overlay (`cli-pet`)** — Gojo Satoru 3D + deteksi otomatis OpenPets (`~/.config/OpenPets/pets/`), otomatis hanya muncul saat terminal fokus (**0% CPU** saat di aplikasi lain).
- **Live Neon Audio Visualizer (`hollow-viz`)** — spektrum audio PipeWire/PulseAudio 36-band bergaya neon ungu–cyan (mode `bars` & `wave`) di tepi bawah desktop, 100% click-through.
- **Volume & Brightness Glass HUD (`hollow-osd`)** — popup indikator volume & kecerahan layar bergaya glassmorphism.
- **Clipboard Manager (`Super+V`) & Quick Dev Panel (`Super+Shift+D`)** — riwayat 40 copy terakhir yang bisa dicari + toggle 1-klik PostgreSQL, MySQL, Mode Fokus/Hemat Baterai, & daftar port lokal aktif.
- **Browser Startpage Lokal** (`projects/hollow-suite/startpage/index.html`) — halaman *New Tab* offline cepat dengan jam live, pintasan `!gh` / `!yt` / `!mdn`, dan shortcut localhost yang bisa diedit.

### Modern Zsh CLI Suite
- `fastfetch` (tema Hollow Purple), `eza` (pengganti `ls` berikon), `bat` (pengganti `cat` berwarna), `zoxide` (`z` smart `cd`), `fzf` + `ripgrep` + `fd`, `btop`, `lazygit` (`lg`), `delta` (git diff side-by-side), `yazi` (`y` file manager 3-panel), `tldr`, dan **Neovim** (`config/nvim/init.lua`).
- **Notifikasi desktop otomatis** saat perintah terminal berjalan ≥ 15 detik + screensaver jam digital neon (`idle` / `jam`).

---

## Cara Pasang (Instalasi Lengkap)

> **Target OS**: Pop!_OS 24.04+ dengan **COSMIC Desktop (Wayland)** (sebagian besar CLI & overlay juga jalan di Ubuntu/Debian Wayland lain yang mendukung `wlr-layer-shell`).

### Langkah 1 — Install Dependensi Sistem
```bash
sudo apt update && sudo apt install -y \
  zsh git curl unzip tar bzip2 neovim fd-find pulseaudio-utils \
  python3 python3-gi python3-cairo python3-pil python3-numpy \
  gir1.2-gtk-3.0 libgtk-layer-shell0
```

### Langkah 2 — Install Oh My Zsh, Powerlevel10k & Plugin Zsh
```bash
# Oh My Zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

# Powerlevel10k & Plugin Zsh
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$ZSH_CUSTOM/themes/powerlevel10k"
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git "$ZSH_CUSTOM/plugins/zsh-syntax-highlighting"
git clone https://github.com/zsh-users/zsh-autosuggestions "$ZSH_CUSTOM/plugins/zsh-autosuggestions"
git clone https://github.com/zsh-users/zsh-completions "$ZSH_CUSTOM/plugins/zsh-completions"

# Jadikan zsh sebagai shell default
chsh -s "$(which zsh)"
```
*(Disarankan menggunakan font **Nerd Font** seperti JetBrainsMono Nerd Font atau FiraCode Nerd Font di pengaturan `cosmic-term` agar semua ikon `eza`, `yazi`, dan prompt tampil sempurna.)*

### Langkah 3 — Install Tool CLI Modern (`fastfetch`, `eza`, `bat`, `zoxide`, `fzf`, `rg`, `btop`, `lazygit`, `delta`, `yazi`, `tldr`)
Jalankan perintah berikut untuk memasang binary x86_64 terbaru langsung ke `~/.local/bin` (tanpa perlu `sudo`):
```bash
mkdir -p ~/.local/bin && python3 - <<'EOF'
import json, shutil, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path

BIN = Path.home() / ".local/bin"
HDR = {"User-Agent": "gojo-theme-installer/1.0", "Accept": "application/vnd.github+json"}

def get_json(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=20).read())

def dl(url, dst):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gojo-theme-installer/1.0"}), timeout=90) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)

SPECS = [
    ("fastfetch-cli/fastfetch", lambda n: "linux-amd64.tar.gz" in n and not n.endswith(".sha256"), ["fastfetch"]),
    ("eza-community/eza",       lambda n: n == "eza_x86_64-unknown-linux-gnu.tar.gz", ["eza"]),
    ("sharkdp/bat",             lambda n: "x86_64-unknown-linux-musl.tar.gz" in n, ["bat"]),
    ("ajeetdsouza/zoxide",      lambda n: "x86_64-unknown-linux-musl.tar.gz" in n, ["zoxide"]),
    ("junegunn/fzf",            lambda n: "linux_amd64.tar.gz" in n, ["fzf"]),
    ("BurntSushi/ripgrep",      lambda n: "x86_64-unknown-linux-musl.tar.gz" in n, ["rg"]),
    ("aristocratos/btop",       lambda n: "x86_64" in n and "linux" in n and n.endswith((".tar.gz", ".tbz")), ["btop"]),
    ("jesseduffield/lazygit",   lambda n: ("linux_x86_64.tar.gz" in n or "Linux_x86_64.tar.gz" in n) and not n.endswith(".txt"), ["lazygit"]),
    ("dandavison/delta",        lambda n: "x86_64-unknown-linux-musl.tar.gz" in n, ["delta"]),
    ("sxyazi/yazi",             lambda n: "x86_64-unknown-linux-musl.zip" in n and n.startswith("yazi-"), ["yazi", "ya"]),
]

for repo, match, bins in SPECS:
    rel = get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    asset = next(a for a in rel["assets"] if match(a["name"]))
    print("Installing:", asset["name"])
    with tempfile.TemporaryDirectory() as td:
        arc = Path(td) / asset["name"]; dl(asset["browser_download_url"], arc)
        out = Path(td) / "o"; out.mkdir()
        if arc.name.endswith(".zip"):
            with zipfile.ZipFile(arc) as zf: zf.extractall(out)
        else:
            with tarfile.open(arc, "r:*") as tf: tf.extractall(out)
        for bn in bins:
            p = next(x for x in out.rglob(bn) if x.is_file() and not x.name.endswith((".1", ".md", ".zsh", ".bash", ".fish")))
            dst = BIN / bn; shutil.copy2(p, dst); dst.chmod(0o755)
        if "btop" in bins:
            tdir = Path.home() / ".config/btop/themes"; tdir.mkdir(parents=True, exist_ok=True)
            for tp in out.rglob("*.theme"): shutil.copy2(tp, tdir / tp.name)

# tealdeer (tldr)
rel = get_json("https://api.github.com/repos/tealdeer-rs/tealdeer/releases/latest")
asset = next(a for a in rel["assets"] if "linux-x86_64-musl" in a["name"] and not a["name"].endswith(".sha256"))
dst = BIN / "tldr"; dl(asset["browser_download_url"], dst); dst.chmod(0o755)
print("Semua CLI modern terpasang!")
EOF
~/.local/bin/tldr --update
```

### Langkah 4 — Clone Repo & Jalankan `./restore.sh`
```bash
git clone https://github.com/Dlann12/gojo_theme_linux.git ~/gojo_theme_linux
cd ~/gojo_theme_linux
chmod +x restore.sh
./restore.sh
```
Script `./restore.sh` akan otomatis:
- Mem-backup `.zshrc` & `.p10k.zsh` lama kamu sebelum menimpa.
- Memasang semua config tema (`COSMIC Dark`, `cosmic-term`, `fastfetch`, `btop`, `bat`, `lazygit`, `yazi`, `nvim`, shortcut COSMIC).
- Menyesuaikan semua path otomatis ke `$HOME` kamu.
- Mengaktifkan service background (`cli-pet`, `hollow-visualizer`, `hollow-clipboard`, `hollow-osd`).

### Langkah 5 — (Opsional) Tambahan Keren
- **Aktifkan Git Delta side-by-side diff**:
  ```bash
  git config --global core.pager delta
  git config --global interactive.diffFilter "delta --color-only"
  git config --global delta.navigate true
  git config --global delta.side-by-side true
  git config --global delta.line-numbers true
  git config --global delta.syntax-theme Dracula
  ```
- **Tambah karakter pet OpenPets lain** (otomatis terdeteksi oleh overlay):
  ```bash
  npx -y install-pet halloween-ghost
  npx -y install-pet vincent-hamster
  npx -y install-pet cache-capy
  pet reload
  ```
- **Pasang Browser Startpage**: buka terminal lalu ketik `startpage`, kemudian salin URL-nya sebagai Homepage / New Tab di Firefox.

---

## Shortcut & Perintah Cepat

| Perintah / Shortcut | Fungsi |
| --- | --- |
| `Super + V` atau `clip` | Buka **Clipboard History** glassmorphism |
| `Super + Shift + D` atau `dev` | Buka **Dev Panel** (PostgreSQL, MySQL, Mode Fokus, Port Aktif) |
| `pet list` / `pet only gojo` / `pet all` | Atur karakter pet 3D yang tampil di terminal |
| `pet feed` / `pat` / `play` / `sleep` | Berinteraksi dengan pet (atau klik kiri/kanan langsung pada pet) |
| `viz mode bars` / `viz mode wave` | Ganti gaya **Live Audio Visualizer** |
| `osd test` | Tes tampilan **Volume / Brightness Glass HUD** |
| `y` | Buka **Yazi** file manager (otomatis `cd` saat keluar) |
| `lg` / `top` / `tldr <cmd>` | Buka **Lazygit** / **btop** / contekan cepat **tldr** |
| `idle` atau `jam` | Screensaver jam digital neon *Hollow Purple* |
| `startpage` | Buka startpage browser lokal |
| `backup-rice` | Update snapshot backup dotfiles |
