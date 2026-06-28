FROM python:3.14-slim
WORKDIR /AstrBot

COPY . /AstrBot/

# Enable pipefail so failures in the NodeSource curl|bash pipe abort the build.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV UV_INSTALL_DIR=/usr/local/bin \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
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
    gnupg \
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
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

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
    && uv pip install socksio pilk --no-cache-dir --system \
    && uv tool install --force ruff \
    && uv tool install --force mypy

RUN mkdir -p /etc/profile.d \
    && cat <<'EOF' >/etc/profile.d/astrbot-dev-tools.sh
export PATH=/usr/local/cargo/bin:$PATH
alias fd='fdfind'
alias bat='batcat'
EOF

EXPOSE 6185

CMD ["python", "main.py"]
