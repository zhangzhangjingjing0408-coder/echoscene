#!/usr/bin/env bash
#
# EchoScene one-click installer.
#
# This script turns a freshly cloned repository into a running local EchoScene:
#   1. installs uv and pnpm if they are missing
#   2. creates an isolated Python 3.12 virtualenv and installs the API + Agent worker
#   3. installs the frontend dependencies and builds the Chrome extension
#   4. copies .env.example -> .env when .env does not exist yet
#   5. on macOS, registers the API and Agent worker as launchd services so they
#      survive reboots and restart on crash
#
# It is safe to re-run: every step is idempotent. Keys are never written by this
# script; you fill the three provider keys into .env afterwards.
#
# Usage:
#   ./scripts/install.sh
#
# The three provider keys you will need (see README):
#   - SUPADATA_API_KEY            (YouTube transcript fallback)
#   - DEEPSEEK_API_KEY            (grounded semantic content)
#   - LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET   (voice coach)

set -euo pipefail

# Resolve the repository root regardless of where the script is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
info() { printf '\033[1;34m[EchoScene]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[EchoScene]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[EchoScene]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[EchoScene]\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Node + pnpm
# ---------------------------------------------------------------------------
ensure_node() {
  if ! have node; then
    die "Node.js 22+ is required but not found. Install it first (https://nodejs.org) and re-run."
  fi
  info "node: $(node --version)"
}

ensure_pnpm() {
  if have pnpm; then
    info "pnpm: $(pnpm --version)"
    return
  fi
  if have corepack; then
    info "pnpm not found — enabling via corepack"
    corepack enable
    corepack prepare pnpm@11.16.0 --activate
  elif have npm; then
    info "pnpm not found — installing globally via npm"
    npm install -g "pnpm@11.16.0"
  else
    die "pnpm is missing and neither corepack nor npm is available. Install Node.js 22+ and re-run."
  fi
  have pnpm || die "pnpm setup failed; make sure your npm global bin directory is on PATH."
  info "pnpm: $(pnpm --version)"
}

# ---------------------------------------------------------------------------
# uv + Python virtualenv
# ---------------------------------------------------------------------------
ensure_uv() {
  if have uv; then
    info "uv: $(uv --version)"
    return
  fi
  info "uv not found — installing into ~/.local/bin"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  have uv || die "uv install failed; add ~/.local/bin to PATH and re-run."
  info "uv: $(uv --version)"
}

setup_venv() {
  if [ -x "$ROOT/.venv/bin/python" ]; then
    info "virtualenv already present at .venv"
  else
    info "creating Python 3.12 virtualenv"
    uv venv --python 3.12 "$ROOT/.venv"
  fi
  info "installing Python dependencies (API + Agent worker)"
  # The `.venv/bin/python` symlink is used deliberately so the venv site-packages resolve.
  "$ROOT/.venv/bin/python" -m pip --version >/dev/null 2>&1 || \
    uv pip install --python "$ROOT/.venv/bin/python" pip >/dev/null
  uv pip install -e ".[agent]"
}

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
build_extension() {
  info "installing frontend dependencies"
  pnpm install
  info "building the Chrome extension"
  pnpm build
  ok "extension built at apps/extension/dist"
}

# ---------------------------------------------------------------------------
# Environment file
# ---------------------------------------------------------------------------
setup_env() {
  if [ -f "$ROOT/.env" ]; then
    info ".env already exists — leaving it untouched"
    return
  fi
  info "creating .env from .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
}

# ---------------------------------------------------------------------------
# macOS launchd services
# ---------------------------------------------------------------------------
PLIST_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/echoscene"
GUI_UID="$(id -u)"
PATH_VALUE="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

write_plist_api() {
  cat > "$PLIST_DIR/com.echoscene.api.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.echoscene.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT/.venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>echoscene_api.main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8787</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH_VALUE</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/api.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/api.err.log</string>
</dict>
</plist>
PLIST
}

write_plist_worker() {
  cat > "$PLIST_DIR/com.echoscene.worker.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.echoscene.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT/.venv/bin/python</string>
        <string>-m</string>
        <string>echoscene_agent.worker</string>
        <string>start</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH_VALUE</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/worker.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/worker.err.log</string>
</dict>
</plist>
PLIST
}

setup_launchd() {
  mkdir -p "$PLIST_DIR" "$LOG_DIR"
  info "writing launchd service definitions"
  write_plist_api
  write_plist_worker

  for label in com.echoscene.api com.echoscene.worker; do
    launchctl bootout "gui/$GUI_UID/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$GUI_UID" "$PLIST_DIR/$label.plist"
    launchctl kickstart -k "gui/$GUI_UID/$label"
  done
  ok "API and Agent worker are running as launchd services"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  info "EchoScene installer — repository: $ROOT"
  ensure_node
  ensure_pnpm
  ensure_uv
  setup_venv
  build_extension
  setup_env

  if [ "$(uname -s)" = "Darwin" ] && [ "${ECHOSCENE_SKIP_SERVICES:-0}" != "1" ]; then
    setup_launchd
  else
    warn "services not auto-started. Run them in two terminals:"
    warn "  API:     .venv/bin/python -m uvicorn echoscene_api.main:app --host 127.0.0.1 --port 8787"
    warn "  Worker:  .venv/bin/python -m echoscene_agent.worker start"
  fi

  ok ""
  ok "Done. Next steps:"
  ok "  1. Edit .env and fill the three provider keys (README has exact steps)."
  ok "  2. Open chrome://extensions -> Developer mode -> Load unpacked -> apps/extension/dist."
  ok "  3. Open a YouTube watch page and click 'Practice with EchoScene'."
  ok "Health check: curl http://127.0.0.1:8787/health"
}

main "$@"
