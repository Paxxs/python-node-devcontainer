# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim@sha256:<PIN_THIS_DIGEST>

ARG TZ=UTC
ARG USERNAME=node
ARG GIT_DELTA_VERSION=0.18.2
ARG AWSCLI_VERSION=2.17.57
ARG UV_VERSION=0.6.6
ARG BUN_VERSION=1.2.5
ARG ZSH_IN_DOCKER_VERSION=1.2.0

ENV TZ=${TZ} \
    DEVCONTAINER=true \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    NPM_CONFIG_PREFIX=/home/node/.npm-global \
    BUN_INSTALL=/home/node/.bun \
    PATH=/home/node/.local/bin:/home/node/.npm-global/bin:/home/node/.bun/bin:${PATH} \
    SHELL=/bin/zsh \
    EDITOR=nano \
    VISUAL=nano

RUN npm config set registry https://registry.npmmirror.com

# ---- system base: keep stable and early ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    less curl wget ca-certificates gnupg2 software-properties-common apt-transport-https lsb-release \
    git git-lfs gh \
    zsh fzf man-db \
    procps htop tree sudo \
    dnsutils net-tools iputils-ping telnet netcat-openbsd iptables ipset iproute2 aggregate \
    unzip zip bzip2 xz-utils \
    jq yq sed gawk \
    ripgrep fd-find \
    build-essential gcc g++ make cmake pkg-config \
    python3 python3-pip python3-venv python3-dev \
    nano tmux neovim \
    openssl libssl-dev \
    libz-dev libffi-dev libbz2-dev libreadline-dev libsqlite3-dev libncurses5-dev libncursesw5-dev liblzma-dev \
    locales \
    chromium \
    fonts-liberation libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 xdg-utils \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3 1 \
    && rm -rf /var/lib/apt/lists/*

RUN chown -R node:node /usr/local/share

# ---- user directories: low change ----
RUN mkdir -p \
    /commandhistory \
    /home/node/.config/gh \
    /home/node/.claude \
    /home/node/.codex \
    /home/node/.gemini \
    /home/node/.npm-global/lib \
    /home/node/.aws \
    /home/node/.wrangler \
    /home/node/.vercel \
    /home/node/.local/bin \
    /usr/local/share/claude-defaults/hooks \
    /usr/local/share/codex-defaults \
    && touch /commandhistory/.bash_history \
    && chown -R node:node \
    /commandhistory \
    /home/node/.config \
    /home/node/.claude \
    /home/node/.codex \
    /home/node/.gemini \
    /home/node/.npm-global \
    /home/node/.aws \
    /home/node/.wrangler \
    /home/node/.vercel \
    /home/node/.local

WORKDIR /workspaces

# ---- install pinned tools as root/user with explicit versions ----
RUN --mount=type=cache,target=/tmp/downloads,sharing=locked \
    ARCH="$(dpkg --print-architecture)" && \
    DEB="/tmp/downloads/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
    if [ ! -f "$DEB" ]; then \
    wget -O "$DEB" "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"; \
    fi && \
    dpkg -i "$DEB"

USER node

RUN echo 'export PATH=$PATH:/home/node/.npm-global/bin:/home/node/.local/bin' >> /home/node/.bashrc && \
    echo 'export PATH=$PATH:/home/node/.npm-global/bin:/home/node/.local/bin' >> /home/node/.zshrc && \
    echo "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" >> /home/node/.bashrc && \
    echo "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" >> /home/node/.zshrc && \
    echo 'alias fd=fdfind' >> /home/node/.zshrc && \
    echo "alias rg='rg --smart-case'" >> /home/node/.zshrc

RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
    -p git \
    -p fzf \
    -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
    -a "source /usr/share/doc/fzf/examples/completion.zsh" \
    -x

RUN ARCH="$(uname -m)" && \
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}-${AWSCLI_VERSION}.zip" -o /tmp/awscliv2.zip && \
    cd /tmp && unzip awscliv2.zip && \
    ./aws/install --install-dir /home/node/.local/aws-cli --bin-dir /home/node/.local/bin && \
    rm -rf /tmp/aws /tmp/awscliv2.zip

RUN curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
RUN curl -fsSL "https://bun.sh/install" | bash -s -- bun-v${BUN_VERSION}

RUN git config --global core.excludesfile ~/.gitignore_global && \
    echo ".claude/settings.local.json" > /home/node/.gitignore_global

USER root

# ---- frequently changed files: keep last ----
COPY scripts/ /usr/local/bin/
COPY templates/settings.json.template /usr/local/share/claude-defaults/settings.json
COPY templates/mcp.json.template /usr/local/share/claude-defaults/mcp.json
COPY templates/session-start.sh.template /usr/local/share/claude-defaults/hooks/session-start.sh
COPY templates/config.toml.template /usr/local/share/codex-defaults/config.toml

RUN chown -R node:node /usr/local/share/claude-defaults /usr/local/share/codex-defaults && \
    chmod 755 \
    /usr/local/bin/init-firewall.sh \
    /usr/local/bin/init-claude-config.sh \
    /usr/local/bin/init-claude-hooks.sh \
    /usr/local/bin/init-codex-config.sh \
    /usr/local/bin/init-opencode-config.sh \
    /usr/local/bin/init-python.sh && \
    printf '%s\n' 'node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh' > /etc/sudoers.d/node-firewall && \
    printf '%s\n' 'node ALL=(root) NOPASSWD: /usr/local/bin/init-claude-config.sh' > /etc/sudoers.d/node-claude-config && \
    printf '%s\n' 'node ALL=(root) NOPASSWD: /usr/local/bin/init-claude-hooks.sh' > /etc/sudoers.d/node-claude-hooks && \
    printf '%s\n' 'node ALL=(root) NOPASSWD: /usr/local/bin/init-codex-config.sh' > /etc/sudoers.d/node-codex-config && \
    printf '%s\n' 'node ALL=(root) NOPASSWD: /usr/local/bin/init-opencode-config.sh' > /etc/sudoers.d/node-opencode-config && \
    printf '%s\n' 'node ALL=(root) NOPASSWD: /usr/local/bin/init-python.sh' > /etc/sudoers.d/node-python && \
    chmod 0440 /etc/sudoers.d/node-*

USER node