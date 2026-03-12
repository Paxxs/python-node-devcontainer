# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install development tools, compilers, and utilities
# Groups: Core utils, Network tools, Build tools, Editors, AI CLI deps, Security
# BuildKit cache mounts for faster rebuilds (5-10x speedup)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities
    less \
    curl \
    wget \
    ca-certificates \
    gnupg2 \
    software-properties-common \
    apt-transport-https \
    lsb-release \
    # Version control
    git \
    git-lfs \
    gh \
    # Shell and terminal tools
    zsh \
    fzf \
    man-db \
    # Process and system tools
    procps \
    htop \
    tree \
    sudo \
    # Network tools
    dnsutils \
    net-tools \
    iputils-ping \
    telnet \
    netcat-openbsd \
    iptables \
    ipset \
    iproute2 \
    aggregate \
    # Archive and compression
    unzip \
    zip \
    bzip2 \
    xz-utils \
    # Text processing and data
    jq \
    yq \
    sed \
    gawk \
    # Fast search tools (modern replacements)
    ripgrep \
    fd-find \
    # Build essentials (for native npm modules)
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    pkg-config \
    # Python (for node-gyp and AI CLIs)
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    # Text editors
    nano \
    tmux \
    neovim \
    # OpenSSL and crypto
    openssl \
    libssl-dev \
    # Additional development libraries
    libz-dev \
    libffi-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libncurses5-dev \
    libncursesw5-dev \
    liblzma-dev \
    # Locales for proper encoding
    locales \
    # Browser automation (Chromium for Chrome DevTools MCP)
    chromium \
    # Chromium dependencies
    fonts-liberation \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils

# Create python symlink for convenience (PEP 394 compliant)
# This allows 'python' command to work in addition to 'python3'
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

# Set up locale (prevents encoding issues with Claude/Codex/Gemini)
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen
ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

# Ensure default node user has access to /usr/local/share
RUN chown -R node:node /usr/local/share

ARG USERNAME=node

# Persist bash history and configure PATH for npm global packages
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USERNAME /commandhistory \
    && echo 'export PATH=$PATH:/home/node/.npm-global/bin:/home/node/.local/bin' >> /home/node/.bashrc \
    && chown node:node /home/node/.bashrc

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create config directories and set permissions
# Note: Workspace directory is created and mounted by VS Code automatically
RUN mkdir -p /home/node/.config/gh /home/node/.claude /home/node/.codex /home/node/.gemini /home/node/.npm-global/lib /home/node/.aws /home/node/.wrangler /home/node/.vercel /home/node/.local/bin && \
    chown -R node:node /home/node/.config /home/node/.claude /home/node/.codex /home/node/.gemini /home/node/.npm-global /home/node/.aws /home/node/.wrangler /home/node/.vercel /home/node/.local

# Default working directory (VS Code will override this with actual workspace mount)
WORKDIR /workspaces

ARG GIT_DELTA_VERSION=0.18.2
RUN --mount=type=cache,target=/tmp/downloads,sharing=locked \
    ARCH="$(dpkg --print-architecture)" && \
    DEB="/tmp/downloads/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
    if [ ! -f "$DEB" ]; then \
    wget -O "$DEB" "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"; \
    fi && \
    sudo dpkg -i "$DEB"

# Set up non-root user
USER node

# Install global packages
ENV NPM_CONFIG_PREFIX=/home/node/.npm-global
ENV PATH=$PATH:/home/node/.npm-global/bin

# Set the default shell to zsh rather than sh
ENV SHELL=/bin/zsh

# Set the default editor and visual
ENV EDITOR=nano
ENV VISUAL=nano

# Default powerline10k theme
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
    -p git \
    -p fzf \
    -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
    -a "source /usr/share/doc/fzf/examples/completion.zsh" \
    -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    -a "export PATH=\$PATH:/home/node/.npm-global/bin:/home/node/.local/bin" \
    -a "alias fd=fdfind" \
    -a "alias rg='rg --smart-case'" \
    -x

# npm CLI packages (Claude Code, Codex, Gemini, Wrangler, Vercel) installed via postCreateCommand
# This ensures packages install AFTER npm-global volume mounts, preventing version conflicts
# See devcontainer.json postCreateCommand for installation details

# Install AWS CLI v2 to volume-persisted location
RUN cd /tmp && \
    curl "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install --install-dir /home/node/.local/aws-cli --bin-dir /home/node/.local/bin && \
    rm -rf awscliv2.zip aws

# Install uv (fast Python package manager)
# uv installer places binary at /home/node/.local/bin/uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> /home/node/.bashrc && \
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> /home/node/.zshrc

# Add .local/bin to PATH for uv and AWS CLI
ENV PATH="/home/node/.local/bin:$PATH"

# Python 3.14 installation moved to init-python.sh (runs via postCreateCommand)
# This ensures installation happens AFTER volume mounts, so it persists correctly
# System Python 3.11 remains available for node-gyp compatibility

# Install bun (fast JavaScript runtime)
RUN curl -fsSL https://bun.sh/install | bash && \
    echo 'export BUN_INSTALL="$HOME/.bun"' >> /home/node/.bashrc && \
    echo 'export PATH="$BUN_INSTALL/bin:$PATH"' >> /home/node/.bashrc && \
    echo 'export BUN_INSTALL="$HOME/.bun"' >> /home/node/.zshrc && \
    echo 'export PATH="$BUN_INSTALL/bin:$PATH"' >> /home/node/.zshrc
ENV BUN_INSTALL="/home/node/.bun"
ENV PATH="$BUN_INSTALL/bin:$PATH"

# Configure git to ignore Claude's local settings (Anthropic best practice)
# This prevents accidentally committing sensitive configuration like API keys
RUN git config --global core.excludesfile ~/.gitignore_global && \
    echo ".claude/settings.local.json" > /home/node/.gitignore_global && \
    chown node:node /home/node/.gitignore_global

# Switch to root for final setup (scripts, sudoers, templates)
USER root

# Create directory for Claude Code and Codex defaults
RUN mkdir -p /usr/local/share/claude-defaults /usr/local/share/claude-defaults/hooks /usr/local/share/codex-defaults

# Copy all scripts and templates in one layer (changes most frequently)
COPY init-firewall.sh /usr/local/bin/
COPY init-claude-config.sh /usr/local/bin/
COPY init-claude-hooks.sh /usr/local/bin/
COPY init-codex-config.sh /usr/local/bin/
COPY init-opencode-config.sh /usr/local/bin/
COPY init-python.sh /usr/local/bin/
COPY patch-claude-toolsearch.py /usr/local/bin/
COPY --chown=node:node settings.json.template /usr/local/share/claude-defaults/settings.json
COPY --chown=node:node mcp.json.template /usr/local/share/claude-defaults/mcp.json
COPY --chmod=755 session-start.sh.template /usr/local/share/claude-defaults/hooks/session-start.sh
COPY --chown=node:node config.toml.template /usr/local/share/codex-defaults/config.toml

# Set permissions and configure sudoers for all init scripts
RUN chmod +x /usr/local/bin/init-firewall.sh && \
    chmod +x /usr/local/bin/init-claude-config.sh && \
    chmod +x /usr/local/bin/init-claude-hooks.sh && \
    chmod +x /usr/local/bin/init-codex-config.sh && \
    chmod +x /usr/local/bin/init-opencode-config.sh && \
    chmod +x /usr/local/bin/init-python.sh && \
    echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall && \
    echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-claude-config.sh" > /etc/sudoers.d/node-claude-config && \
    echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-claude-hooks.sh" > /etc/sudoers.d/node-claude-hooks && \
    echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-codex-config.sh" > /etc/sudoers.d/node-codex-config && \
    echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-opencode-config.sh" > /etc/sudoers.d/node-opencode-config && \
    echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-python.sh" > /etc/sudoers.d/node-python && \
    chmod 0440 /etc/sudoers.d/node-firewall && \
    chmod 0440 /etc/sudoers.d/node-claude-config && \
    chmod 0440 /etc/sudoers.d/node-claude-hooks && \
    chmod 0440 /etc/sudoers.d/node-codex-config && \
    chmod 0440 /etc/sudoers.d/node-opencode-config && \
    chmod 0440 /etc/sudoers.d/node-python

# Switch back to node user for runtime
USER node
