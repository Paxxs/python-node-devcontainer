#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=================================================="
echo "MCP Transport Test Script"
echo "Test: Context7 & Cloudflare Docs via mcp-remote"
echo "=================================================="
echo ""

# Check if mcp.json exists
if [ ! -f ~/.claude/mcp.json ]; then
    echo -e "${RED}Error: ~/.claude/mcp.json not found${NC}"
    echo "Run: claude mcp add --transport sse context7 https://mcp.context7.com/sse"
    exit 1
fi

echo -e "${YELLOW}Current MCP configuration:${NC}"
cat ~/.claude/mcp.json | jq '.'
echo ""

# Backup
BACKUP_FILE=~/.claude/mcp.json.backup.$(date +%s)
echo -e "${GREEN}Creating backup: $BACKUP_FILE${NC}"
cp ~/.claude/mcp.json "$BACKUP_FILE"
echo ""

# Show what will be done
echo -e "${YELLOW}This script will:${NC}"
echo "1. Remove existing SSE-based servers (context7, cf-docs)"
echo "2. Test Context7 with mcp-remote (may or may not work)"
echo "3. Test Cloudflare Docs with mcp-remote (known to work)"
echo "4. Show which servers support mcp-remote transport"
echo ""
echo -e "${YELLOW}About mcp-remote:${NC}"
echo "- Uses stdio transport with npx mcp-remote wrapper"
echo "- May require OAuth authentication on first use (browser opens)"
echo "- Connects to /mcp endpoint instead of /sse"
echo ""
echo -e "${YELLOW}Endpoints to test:${NC}"
echo "- Context7: https://mcp.context7.com/mcp (unknown if supported)"
echo "- Cloudflare: https://docs.mcp.cloudflare.com/mcp (known to work)"
echo ""
echo -e "${YELLOW}To restore backup if needed:${NC}"
echo "  cp $BACKUP_FILE ~/.claude/mcp.json"
echo ""

read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo -e "${GREEN}Step 1: Removing existing SSE servers...${NC}"
claude mcp remove context7 2>/dev/null || echo "  (context7 not found, skipping)"
claude mcp remove cf-docs 2>/dev/null || echo "  (cf-docs not found, skipping)"
echo ""

echo -e "${GREEN}Step 2: Testing Context7 with mcp-remote...${NC}"
echo "  Endpoint: https://mcp.context7.com/mcp"
echo "  Running: claude mcp add --transport stdio context7 -- npx mcp-remote https://mcp.context7.com/mcp"
echo ""

if claude mcp add --transport stdio context7 -- npx mcp-remote https://mcp.context7.com/mcp 2>&1; then
    echo ""
    echo -e "  ${GREEN}✓ Context7 mcp-remote appears to work!${NC}"
else
    echo ""
    echo -e "  ${YELLOW}⚠ Context7 mcp-remote may not be supported${NC}"
    echo "  (Check 'claude mcp list' output below for status)"
fi
echo ""

echo -e "${GREEN}Step 3: Testing Cloudflare Docs with mcp-remote...${NC}"
echo "  Endpoint: https://docs.mcp.cloudflare.com/mcp"
echo "  Running: claude mcp add --transport stdio cf-docs -- npx mcp-remote https://docs.mcp.cloudflare.com/mcp"
echo ""

if claude mcp add --transport stdio cf-docs -- npx mcp-remote https://docs.mcp.cloudflare.com/mcp 2>&1; then
    echo ""
    echo -e "  ${GREEN}✓ Cloudflare Docs mcp-remote configured${NC}"
else
    echo ""
    echo -e "  ${RED}✗ Cloudflare Docs mcp-remote failed${NC}"
fi
echo ""

echo -e "${GREEN}Step 4: Verifying configuration...${NC}"
echo ""
echo -e "${YELLOW}MCP servers list:${NC}"
claude mcp list
echo ""

echo -e "${YELLOW}New configuration JSON:${NC}"
cat ~/.claude/mcp.json | jq '.'
echo ""

echo -e "${GREEN}✓ Configuration updated!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Restart Claude Code to pick up changes"
echo "2. Check 'claude mcp list' output above for server status"
echo "3. First query may prompt OAuth authentication (browser opens)"
echo "4. Test queries:"
echo "   - Context7: 'Find Next.js documentation'"
echo "   - Cloudflare: 'Search Cloudflare docs for Workers KV'"
echo ""
echo -e "${YELLOW}Determining which method worked:${NC}"
echo "- Look at 'claude mcp list' output above"
echo "- Status 'connected' = working"
echo "- Status 'error' or 'disconnected' = not supported, needs SSE"
echo ""
echo -e "${YELLOW}If servers don't work with mcp-remote:${NC}"
echo "1. Restore backup: cp $BACKUP_FILE ~/.claude/mcp.json"
echo "2. Re-add with SSE transport:"
echo "   claude mcp add --transport sse context7 https://mcp.context7.com/sse"
echo "   claude mcp add --transport sse cf-docs https://docs.mcp.cloudflare.com/sse"
echo ""
echo -e "${YELLOW}Expected results:${NC}"
echo "- Context7: May or may not support mcp-remote (unknown)"
echo "- Cloudflare Docs: Should work with mcp-remote (documented)"
echo ""
