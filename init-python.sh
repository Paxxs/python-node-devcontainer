#!/bin/bash
set -euo pipefail

echo "=== Python 3.14 Setup ==="

WORKSPACE_FOLDER="${CONTAINERWSF:-/workspaces/claude-code-devcontainers}"
UV_BIN="${HOME}/.local/bin/uv"

if [ ! -x "$UV_BIN" ]; then
  echo "uv not found: $UV_BIN"
  exit 1
fi

if [ ! -d "$WORKSPACE_FOLDER" ]; then
  echo "Workspace folder not found: $WORKSPACE_FOLDER"
  exit 1
fi

echo "Configuring uv package index..."
mkdir -p "${HOME}/.config/uv"
cat > "${HOME}/.config/uv/uv.toml" <<'EOF'
[[index]]
url = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/"
default = true
EOF

echo "Installing Python 3.14 via uv..."
"$UV_BIN" python install 3.14

echo "Pinning Python 3.14 for the project..."
cd "$WORKSPACE_FOLDER"
"$UV_BIN" python pin 3.14

PYTHON314_PATH="$("$UV_BIN" python find 3.14)"
echo "Python 3.14 installed at: $PYTHON314_PATH"

echo "Making python3.14 available in user PATH..."
mkdir -p "${HOME}/.local/bin"
ln -sf "$PYTHON314_PATH" "${HOME}/.local/bin/python3.14"
ln -sf "$PYTHON314_PATH" "${HOME}/.local/bin/python"

if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "${HOME}/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
fi

echo "Configuring pip mirror..."
"${HOME}/.local/bin/python" -m pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

echo "Verifying installation..."
"${HOME}/.local/bin/python" --version
"${HOME}/.local/bin/python3.14" --version

echo ""
echo "Available Python versions:"
"$UV_BIN" python list

echo "Done. Reopen shell or run: export PATH=\"$HOME/.local/bin:\$PATH\""