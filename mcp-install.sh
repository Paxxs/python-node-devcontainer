#!/bin/bash

echo "Installing MCP servers for Claude Code..."
echo ""

# Add Context7 MCP server (using mcp-remote for stdio transport)
echo "Adding Context7 (library documentation)..."
claude mcp add --transport stdio context7 -- npx mcp-remote https://mcp.context7.com/mcp
echo
echo "or"
echo "claude mcp add --transport http context7 https://mcp.context7.com/mcp --header "CONTEXT7_API_KEY: YOUR_API_KEY"
echo ""
echo "✓ Context7 added"
echo ""

# Add Cloudflare Docs MCP server (using mcp-remote for stdio transport)
echo "Adding Cloudflare Docs..."
claude mcp add --transport stdio cf-docs -- npx mcp-remote https://docs.mcp.cloudflare.com/mcp
echo "✓ Cloudflare Docs added"
echo ""

# Optional Chrome DevTools MCP server (requires Chromium)
# Note: Docker-specific flags required for containerized Chromium
echo "Adding Chrome DevTools MCP server (optional)..."
claude mcp add --transport stdio chrome-devtools npx chrome-devtools-mcp@latest -- \
  --executablePath=/usr/bin/chromium \
  --headless \
  --chromeArg='--no-sandbox' \
  --chromeArg='--disable-setuid-sandbox' \
  --chromeArg='--disable-dev-shm-usage'
echo "✓ Chrome DevTools added"

echo "Done! Verifying installation..."
echo ""
claude mcp list
echo ""
echo "MCP servers installed successfully!"
echo "You can now ask Claude Code about Next.js, MongoDB, Cloudflare Workers, etc."
