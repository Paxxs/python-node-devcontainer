#!/bin/bash
set -euo pipefail

# Get workspace folder from environment or default
WORKSPACE_FOLDER="${CONTAINERWSF:-/workspaces/claude-code-devcontainers}"
WORKSPACE_HOOKS="$WORKSPACE_FOLDER/.claude/hooks"
TEMPLATE_DIR="/usr/local/share/claude-defaults/hooks"

echo "Initializing Claude Code hooks..."

# Create .claude/hooks directory in workspace if it doesn't exist
if [ ! -d "$WORKSPACE_HOOKS" ]; then
    echo "Creating $WORKSPACE_HOOKS directory..."
    mkdir -p "$WORKSPACE_HOOKS"
fi

# Copy session-start hook template if it doesn't exist
if [ ! -f "$WORKSPACE_HOOKS/session-start.sh" ]; then
    if [ -f "$TEMPLATE_DIR/session-start.sh" ]; then
        echo "Installing session-start hook..."
        cp "$TEMPLATE_DIR/session-start.sh" "$WORKSPACE_HOOKS/"
        chmod +x "$WORKSPACE_HOOKS/session-start.sh"
        echo "✓ Session-start hook installed at $WORKSPACE_HOOKS/session-start.sh"
    else
        echo "Warning: Hook template not found at $TEMPLATE_DIR/session-start.sh"
    fi
else
    echo "Session-start hook already exists, preserving user customizations"
    # Ensure it's executable even if it already exists
    chmod +x "$WORKSPACE_HOOKS/session-start.sh"
fi

# Set ownership to node user
chown -R node:node "$WORKSPACE_FOLDER/.claude" 2>/dev/null || true

# path claude
host="${API_HOST:-anyrouter.top}"

claude_cli="$(command -v claude || true)"
if [[ -z "$claude_cli" ]]; then
  echo "Error: claude command not found in PATH" >&2
  exit 1
fi

resolve_realpath() {
  python3 - <<'PY' "$1"
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}

target="$(resolve_realpath "$claude_cli")"

if [[ ! -f "$target" ]]; then
  echo "Error: target is not a regular file: $target" >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin)
    sed -i '' "s/\"api.anthropic.com\"/\"$host\"/g" "$target"
    ;;
  Linux)
    sed -i "s/\"api.anthropic.com\"/\"$host\"/g" "$target"
    ;;
  *)
    echo "错误：不支持的操作系统" >&2
    exit 1
    ;;
esac
echo "patched: $target"

echo "Claude Code hooks initialization complete"
