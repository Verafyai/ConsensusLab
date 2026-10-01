#!/usr/bin/env bash
# launch.sh: start Consensus Lab as a herdr session (spec §10). Run from anywhere.
#
#   harness/launch.sh            open the "Consensus Lab" workspace in herdr (via herdr-plus)
#   harness/launch.sh --dry-run  show what would happen, change nothing
#   harness/launch.sh --tmux     use tmux instead of herdr (fallback)
#
# Panes: orchestrator · claude (experimenter live stream) · grok (@VerafyAI) · dashboard ·
# monitor. Follows the Collective's convention: a herdr-plus project template installed
# into herdr-plus's projects/ folder, then `herdr-plus open`. herdr must be running: if
# you're not inside herdr yet, run `herdr` in this folder, then this script in its pane.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"; MODE=herdr; DRY=0; NAME="Consensus Lab"
while [ $# -gt 0 ]; do
  case "$1" in
    --tmux) MODE=tmux;; --dry-run) DRY=1;;
    -h|--help) sed -n '2,12p' "$0"; exit 0;;
    *) echo "unknown option: $1"; exit 1;;
  esac; shift
done
run() { if [ $DRY = 1 ]; then echo "  DRY: $*"; else eval "$@"; fi; }
say() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
die() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

say "Consensus Lab"
[ -f CHARTER.md ] || die "can't find the lab (no CHARTER.md in $ROOT)"
[ -f ops/STOP ] && die "ops/STOP is present: the lab is stopped. Remove it to launch."

say "1) Prerequisites"
need=(uv git claude)
[ $MODE = herdr ] && need+=(herdr) || need+=(tmux)
miss=0
for c in "${need[@]}"; do
  if command -v "$c" >/dev/null 2>&1; then ok "$c"; else warn "$c not found"; miss=1; fi
done
[ $miss = 1 ] && [ $DRY = 0 ] && die "install what's missing, then re-run"
[ -f .env ] && ok ".env present" || warn ".env missing: copy .env.example (see ops/queue/G-003)"
if uv run python -m lab check >/dev/null 2>&1; then ok "budgets and prices set"
else warn "budgets/prices not set: the orchestrator will refuse to run (ops/queue/G-001)"; fi
chmod +x harness/panes/*.sh 2>/dev/null || true

if [ $MODE = herdr ]; then
  say "2) herdr"
  cfg="$(herdr plugin config-dir cloudmanic.herdr-plus 2>/dev/null || true)"
  if [ -z "$cfg" ]; then
    run "herdr plugin install cloudmanic/herdr-plus" && ok "installed herdr-plus"
    cfg="$(herdr plugin config-dir cloudmanic.herdr-plus 2>/dev/null || true)"
  else ok "herdr-plus plugin installed"; fi
  [ -z "$cfg" ] && [ $DRY = 0 ] && die "couldn't find herdr-plus's config folder (herdr ≥ 0.7)"
  cfg="${cfg:-<herdr-plus config dir>}"
  HP="$(command -v herdr-plus 2>/dev/null || true)"
  if [ -z "$HP" ]; then
    for d in "$HOME/.config/herdr" "$HOME/Library/Application Support/herdr" "$HOME/.local/share/herdr"; do
      [ -d "$d" ] || continue
      HP="$(find "$d" -type f -name herdr-plus -perm -u+x 2>/dev/null | head -1)"
      [ -n "$HP" ] && break
    done
  fi
  if [ -z "$HP" ] && [ $DRY = 0 ]; then
    warn "the herdr-plus program wasn't found. Install it, then re-run:"
    echo "       brew tap cloudmanic/herdr-plus https://github.com/cloudmanic/herdr-plus"
    echo "       brew install cloudmanic/herdr-plus/herdr-plus"
    exit 1
  fi
  run "mkdir -p '$cfg/projects' && sed 's|__LAB_ROOT__|$ROOT|' harness/herdr/consensus-lab.toml > '$cfg/projects/consensus-lab.toml'"
  ok "workspace template installed: \"$NAME\""
  if [ $DRY = 1 ]; then echo "  DRY: herdr-plus open \"$NAME\""; exit 0; fi
  if "$HP" open "$NAME"; then
    ok "opened \"$NAME\". Dashboard: http://127.0.0.1:${CL_DASHBOARD_PORT:-8770}/"
    exit 0
  fi
  warn "herdr isn't running here yet. Run:  herdr   then  harness/launch.sh  in its first pane."
  warn "Or skip herdr:  harness/launch.sh --tmux"
  exit 1
fi

say "2) tmux (fallback)"
S=consensus-lab
if tmux has-session -t $S 2>/dev/null; then ok "session '$S' already running"; [ $DRY = 1 ] || exec tmux attach -t $S; exit 0; fi
run "tmux new-session -d -s $S -n lab -c '$ROOT' 'harness/panes/orchestrator.sh'"
run "tmux split-window -h -t $S:lab -c '$ROOT' 'harness/panes/claude.sh'"
run "tmux split-window -v -t $S:lab.1 -c '$ROOT' 'harness/panes/grok.sh'"
run "tmux split-window -v -t $S:lab.2 -c '$ROOT' 'harness/panes/dashboard.sh'"
run "tmux split-window -v -t $S:lab.0 -c '$ROOT' 'harness/panes/monitor.sh'"
[ $DRY = 1 ] || exec tmux attach -t $S
