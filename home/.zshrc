# Ensure ~/.local/bin is in PATH early for startup tools
export PATH="$HOME/.local/bin:$PATH"

# Startup
if [[ -o interactive && -t 1 ]] && command -v fastfetch >/dev/null 2>&1; then
  fastfetch
fi

# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# oh-my-zsh
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="powerlevel10k/powerlevel10k"

# Plugins
plugins=(git ubuntu zsh-syntax-highlighting zsh-autosuggestions zsh-completions)

source $ZSH/oh-my-zsh.sh
autoload -U compinit && compinit

# Powerlevel10k
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# Alias Manajemen Package
alias update="sudo apt update && sudo apt upgrade -y"
alias install="sudo apt install"
alias remove="sudo apt remove"
alias purge="sudo apt purge"
alias autoremove="sudo apt autoremove -y && sudo apt autoclean"

# Alias PostgreSQL & MySQL
alias start_pgsql="sudo systemctl start postgresql"
alias stop_pgsql="sudo systemctl stop postgresql"
alias status_pgsql="sudo systemctl status postgresql"
alias start_mysql="sudo systemctl start mysql"
alias stop_mysql="sudo systemctl stop mysql"
alias status_mysql="sudo systemctl status mysql"

# Git Aliases
alias g='git'
alias gs='git status'
alias ga='git add'
alias gaa='git add .'
alias gc='git commit -m'
alias gp='git push'
alias gl='git pull'

# Composer Global Bin Path
export PATH="$HOME/.config/composer/vendor/bin:$PATH"

# NVM Configuration
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"


# Added by Antigravity CLI installer
export PATH="/home/kerja/.local/bin:$PATH"

# >>> hollow-suite modern cli >>>
# Modern ls (eza) with icons & git status
if command -v eza >/dev/null 2>&1; then
  alias ls='eza --icons --group-directories-first'
  alias ll='eza -la --icons --git --group-directories-first'
  alias la='eza -a --icons --group-directories-first'
  alias lt='eza --tree --level=2 --icons'
fi

# Modern cat (bat) with syntax highlighting
if command -v bat >/dev/null 2>&1; then
  alias cat='bat --paging=never'
  alias catp='bat'
fi

# Smart cd (zoxide)
if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init zsh)"
fi

# Fuzzy Finder (fzf) with Hollow Purple theme + fd & bat preview
if command -v fzf >/dev/null 2>&1; then
  export FZF_DEFAULT_COMMAND='fd --type f --strip-cwd-prefix --hidden --follow --exclude .git'
  export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
  export FZF_CTRL_T_OPTS="--preview 'bat --color=always --line-range=:120 {}'"
  export FZF_DEFAULT_OPTS="--height=45% --layout=reverse --border=rounded --color=bg+:#2e1f4d,fg+:#f8fafc,hl:#38bdf8,hl+:#c084fc,border:#c084fc,prompt:#c084fc,pointer:#38bdf8,marker:#34d399,info:#94a3b8"
  source <(fzf --zsh)
fi

# Visual Git, System Monitor, File Manager & Hollow Suite Panels
alias lg='lazygit'
alias top='btop'
alias dev='dev-panel >/dev/null 2>&1 &'
alias clip='clip-panel >/dev/null 2>&1 &'
alias viz='hollow-viz'
alias osd='hollow-osd'
alias idle='hollow-clock'
alias jam='hollow-clock'
alias startpage='xdg-open /home/kerja/.gemini/antigravity/scratch/hollow-suite/startpage/index.html >/dev/null 2>&1 &'

# Yazi file manager wrapper: automatically cd into directory on quit
if command -v yazi >/dev/null 2>&1; then
  function y() {
    local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
    yazi "$@" --cwd-file="$tmp"
    IFS= read -r -d '' cwd < "$tmp"
    [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
    rm -f -- "$tmp"
  }
fi

# Auto desktop notification when a command runs >= 15s
autoload -Uz add-zsh-hook
_hollow_cmd_start=0
_hollow_cmd_text=""
function _hollow_preexec() {
  _hollow_cmd_start=$SECONDS
  _hollow_cmd_text="$1"
}
function _hollow_precmd() {
  local rc=$?
  if (( _hollow_cmd_start > 0 )); then
    local dur=$(( SECONDS - _hollow_cmd_start ))
    local cmd_first="${_hollow_cmd_text%% *}"
    _hollow_cmd_start=0
    if (( dur >= 15 )); then
      case "$cmd_first" in
        vim|nvim|nano|btop|top|htop|lazygit|lg|y|yazi|idle|jam|hollow-clock|ssh|man|less|catp|tmux|watch) ;;
        *)
          if command -v hollow-notify >/dev/null 2>&1; then
            local title="✓ Selesai (${dur}d)"
            (( rc != 0 )) && title="✕ Error kode ${rc} (${dur}d)"
            hollow-notify "$title" "${_hollow_cmd_text:0:90}" "$rc" >/dev/null 2>&1 &!
          fi
          ;;
      esac
    fi
  fi
}
add-zsh-hook preexec _hollow_preexec
add-zsh-hook precmd _hollow_precmd
# <<< hollow-suite modern cli <<<
