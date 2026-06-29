FROM python:3.14-slim
WORKDIR /AstrBot

COPY . /AstrBot/

# Enable pipefail so failures in install pipes abort the build.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV UV_INSTALL_DIR=/usr/local/bin \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    NVM_DIR=/root/.nvm \
    BASH_ENV=/root/.bash_env \
    PATH=/usr/local/cargo/bin:${PATH} \
    XDG_BIN_HOME=/usr/local/bin \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    ca-certificates \
    bash \
    ffmpeg \
    libavcodec-extra \
    curl \
    dnsutils \
    file \
    less \
    lsof \
    netcat-openbsd \
    openssh-client \
    procps \
    iproute2 \
    iputils-ping \
    git \
    gh \
    fzf \
    zsh \
    shellcheck \
    zip \
    unzip \
    tree \
    rsync \
    sqlite3 \
    strace \
    psmisc \
    mtr-tiny \
    vim-common \
    xxd \
    ripgrep \
    fd-find \
    jq \
    bat \
    eza \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN touch "${BASH_ENV}" \
    && echo '. "${BASH_ENV}"' >> ~/.bashrc \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.5/install.sh | PROFILE="${BASH_ENV}" bash \
    && source "${BASH_ENV}" \
    && nvm install node \
    && nvm alias default node \
    && npm install -g corepack \
    && corepack enable \
    && current_node_dir="$(dirname "$(dirname "$(nvm which current)")")" \
    && for tool in node npm npx corepack pnpm; do \
        if [[ -x "${current_node_dir}/bin/${tool}" ]]; then \
            ln -sf "${current_node_dir}/bin/${tool}" "/usr/local/bin/${tool}"; \
        fi; \
    done \
    && node --version \
    && npm --version \
    && corepack --version

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
    sh -s -- -y --profile minimal --default-toolchain stable \
    && cargo --version \
    && tmpdir="$(mktemp -d)" \
    && curl -L --proto '=https' --tlsv1.2 -sSf \
        https://github.com/cargo-bins/cargo-binstall/releases/latest/download/cargo-binstall-x86_64-unknown-linux-musl.tgz \
        | tar -C "$tmpdir" -xzf - \
    && install -m 0755 "$tmpdir/cargo-binstall" /usr/local/cargo/bin/cargo-binstall \
    && rm -rf "$tmpdir" \
    && cargo binstall --no-confirm \
        git-delta \
        du-dust \
        procs \
        tokei \
        hyperfine \
        sd \
        xh \
        tealdeer

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv --version \
    && echo "3.14" > .python-version \
    && uv lock \
    && uv export --format requirements.txt --output-file requirements.txt --frozen \
    && uv pip install -r requirements.txt --no-cache-dir --system \
    && uv pip install socksio pilk --no-cache-dir --system

RUN cd /AstrBot/dashboard \
    && pnpm install --frozen-lockfile \
    && pnpm build \
    && rm -rf /AstrBot/astrbot/dashboard/dist \
    && mkdir -p /AstrBot/astrbot/dashboard \
    && cp -r dist /AstrBot/astrbot/dashboard/

RUN mkdir -p /etc/profile.d \
    && cat <<'EOF' >/etc/profile.d/astrbot-dev-tools.sh
export PATH=/usr/local/cargo/bin:$PATH
export NVM_DIR=/root/.nvm
if [ -s "$NVM_DIR/nvm.sh" ]; then
  . "$NVM_DIR/nvm.sh"
fi
alias fd='fdfind'
alias bat='batcat'
EOF

EXPOSE 6185

CMD ["python", "main.py"]
