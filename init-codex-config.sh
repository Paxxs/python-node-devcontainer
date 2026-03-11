#!/bin/bash
set -euo pipefail

CODEX_HOME="/home/node/.codex"
CONFIG_FILE="$CODEX_HOME/config.toml"
CONFIG_TEMPLATE="/usr/local/share/codex-defaults/config.toml"

echo "Initializing Codex CLI configuration..."

# Create .codex directory if it doesn't exist
if [ ! -d "$CODEX_HOME" ]; then
    echo "Creating $CODEX_HOME directory..."
    mkdir -p "$CODEX_HOME"
    chown node:node "$CODEX_HOME"
fi

# Copy config template if it doesn't exist
if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$CONFIG_TEMPLATE" ]; then
        echo "Copying Codex CLI configuration from template..."
        bash -c "cat '$CONFIG_TEMPLATE' > '$CONFIG_FILE'"
        chown node:node "$CONFIG_FILE"
        echo "✓ Codex sandbox disabled (Docker container isolation used instead)"
        echo "  sandbox_mode: danger-full-access"
        echo "  approval_policy: never"
    else
        echo "Warning: Codex config template not found at $CONFIG_TEMPLATE"
    fi
else
    echo "Codex config already exists, preserving user settings"
fi

echo "Codex CLI configuration complete"
