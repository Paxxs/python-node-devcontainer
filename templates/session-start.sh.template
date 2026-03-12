#!/bin/bash
# SessionStart Hook - DevContainer Environment Check
# This hook runs at the start of each Claude Code session to verify devcontainer setup

set -e

echo "🔍 Claude Code DevContainer - Environment Check"
echo "================================================"

# Detect if running in a devcontainer
# Uses multiple detection methods for reliability:
# 1. REMOTE_CONTAINERS_IPC - VS Code devcontainer environment variable (most reliable)
# 2. CODESPACES - GitHub Codespaces environment variable
# 3. /.dockerenv - File present in most Docker containers
# 4. cgroups - Fallback check (may not work in all container configurations)
IN_DEVCONTAINER=false

if [[ -n "${REMOTE_CONTAINERS_IPC}" ]] || \
   [[ -n "${CODESPACES}" ]] || \
   [[ -f "/.dockerenv" ]] || \
   grep -qa "docker\|lxc" /proc/1/cgroup 2>/dev/null; then
    IN_DEVCONTAINER=true
fi

if [[ "$IN_DEVCONTAINER" == "true" ]]; then
    echo "✅ Running inside devcontainer"
    echo ""
    echo "INSTRUCTION FOR CLAUDE: Greet the user and confirm they are running in a properly configured devcontainer environment with all tools available."
    echo ""

    # Show container info
    if [[ -n "${HOSTNAME}" ]]; then
        echo "📦 Container: $HOSTNAME"
    fi

    # Check volume mounts (matches devcontainer.json mounts section)
    echo ""
    echo "💾 Volume Mounts:"
    for volume in ".claude" ".codex" ".gemini" ".opencode" ".config/gh" ".npm-global" ".cargo" ".bun" ".local" ".aws" ".wrangler" ".vercel"; do
        if [[ -d "/home/node/$volume" ]]; then
            echo "   ✅ $volume"
        else
            echo "   ❌ $volume (not found)"
        fi
    done

    # Check bash history volume (separate mount point)
    if [[ -d "/commandhistory" ]]; then
        echo "   ✅ commandhistory"
    else
        echo "   ❌ commandhistory (not found)"
    fi

    # Check MCP servers configuration
    echo ""
    echo "🔌 MCP Servers:"
    MCP_FILE="/home/node/.claude/mcp.json"
    if [[ -f "$MCP_FILE" ]]; then
        # Extract server names from mcp.json
        MCP_SERVERS=$(jq -r '.mcpServers | keys[]' "$MCP_FILE" 2>/dev/null || echo "")
        if [[ -n "$MCP_SERVERS" ]]; then
            while IFS= read -r server; do
                echo "   ✅ $server"
            done <<< "$MCP_SERVERS"
        else
            echo "   ℹ️  No MCP servers configured"
        fi
    else
        echo "   ⚠️  mcp.json not found (run init-claude-config.sh)"
    fi

    # Check tool availability (excluding docker - not available inside devcontainer)
    echo ""
    echo "🛠️  Tools:"
    for tool in claude codex gemini opencode gh aws uv; do
        if command -v "$tool" &> /dev/null; then
            VERSION=$("$tool" --version 2>&1 | head -n1 || echo "installed")
            echo "   ✅ $tool ($VERSION)"
        else
            echo "   ❌ $tool (not found)"
        fi
    done

    # Check network configuration
    echo ""
    echo "🌐 Network:"
    if ip addr show 2>/dev/null | grep -q "inet.*eth0"; then
        ETH0_IP=$(ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
        echo "   ✅ Container IP: $ETH0_IP"
    fi

    # Check if on expected Docker network
    if [[ -n "${OTEL_EXPORTER_OTLP_ENDPOINT}" ]]; then
        echo "   ✅ OpenTelemetry: $OTEL_EXPORTER_OTLP_ENDPOINT"
    fi

    # Show current workspace
    echo ""
    echo "📁 Workspace: $(pwd)"

    # Git status check
    if git rev-parse --git-dir > /dev/null 2>&1; then
        BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
        echo "   ✅ Git branch: $BRANCH"

        # Check if on main/master (remind about feature branches)
        if [[ "$BRANCH" == "main" ]] || [[ "$BRANCH" == "master" ]]; then
            echo "   ⚠️  You're on $BRANCH - consider creating a feature branch"
        fi
    fi

else
    # Running OUTSIDE devcontainer
    echo "⚠️  WARNING: Not running in devcontainer!"
    echo ""
    echo "INSTRUCTION FOR CLAUDE: IMMEDIATELY WARN the user they are NOT in a devcontainer and should reopen in container for full functionality."
    echo ""
    echo "This project is designed to run in a devcontainer environment."
    echo ""
    echo "To open in devcontainer:"
    echo "  1. Open VS Code"
    echo "  2. Install 'Dev Containers' extension"
    echo "  3. Run: Dev Containers: Reopen in Container"
    echo ""
    echo "Or from command line:"
    echo "  devcontainer up --workspace-folder ."
    echo ""
    echo "Session will continue, but some features may not work correctly."
    echo ""
fi

echo "================================================"
echo "Ready to code! 🚀"
echo ""

# Quick reference commands
if [[ "$IN_DEVCONTAINER" == "true" ]]; then
    echo "Quick commands:"
    echo "  - git status                    # Check git status"
    echo "  - claude --version              # Check Claude version"
    echo "  - cat CLAUDE.md                 # View project guide"
    echo "  - ls -la ~/.claude/             # View Claude config"
    echo ""
fi
