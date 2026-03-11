#!/usr/bin/env bash
#
# OpenCode Configuration Initialization Script
#
# Purpose: Initialize OpenCode configuration for devcontainer environment
# This script runs during container creation (postCreateCommand) to set up
# OpenCode's configuration directory and provide default settings.
#
# OpenCode is provider-agnostic and supports:
# - Anthropic (Claude)
# - OpenAI
# - Google (Gemini)
# - Local models
#
# Users should configure their preferred provider via:
# - Environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY)
# - opencode config commands
#

set -e

echo "🔧 Initializing OpenCode configuration..."

# Ensure OpenCode config directory exists
OPENCODE_DIR="/home/node/.opencode"
if [ ! -d "$OPENCODE_DIR" ]; then
    echo "📁 Creating OpenCode config directory: $OPENCODE_DIR"
    mkdir -p "$OPENCODE_DIR"
    chown -R node:node "$OPENCODE_DIR"
fi

echo "✅ OpenCode configuration initialized"
echo ""
echo "📝 To configure OpenCode, set your preferred AI provider:"
echo ""
echo "   Option 1: Anthropic (Claude)"
echo "   export ANTHROPIC_API_KEY=your_api_key"
echo ""
echo "   Option 2: OpenAI"
echo "   export OPENAI_API_KEY=your_api_key"
echo ""
echo "   Option 3: Google (Gemini)"
echo "   export GOOGLE_API_KEY=your_api_key"
echo ""
echo "   Or use: opencode config set provider <anthropic|openai|google>"
echo ""
