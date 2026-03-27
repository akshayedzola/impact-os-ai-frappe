# ── python:3.14-slim-bookworm — Frappe v16.12+ requires Python>=3.14,<3.15 ───
FROM python:3.14-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# ── ALL system deps (sourced from github.com/frappe/frappe_docker) ────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core
    git curl wget sudo locales \
    build-essential make \
    # MariaDB / Postgres clients
    mariadb-client \
    default-libmysqlclient-dev \
    libmariadb-dev \
    # Redis
    redis-tools \
    # PDF / fonts
    libssl-dev \
    fonts-cantarell \
    xfonts-75dpi \
    xfonts-base \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    # Python build deps
    libffi-dev \
    libbz2-dev \
    libsqlite3-dev \
    libreadline-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libldap2-dev \
    libsasl2-dev \
    liblcms2-dev \
    libtiff5-dev \
    libwebp-dev \
    liblzma-dev \
    zlib1g-dev \
    tk-dev \
    tk8.6-dev \
    xz-utils \
    llvm \
    # Other
    cron \
    pkg-config \
    gettext-base \
    netcat-openbsd \
    file \
    ca-certificates \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ── Node 24 via NodeSource (Frappe v16.12 package.json: "node": ">=24") ──────
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn \
    && rm -rf /var/lib/apt/lists/*

# ── wkhtmltopdf (same version as official Frappe image) ──────────────────────
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/') \
    && FILE=wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${ARCH}.deb \
    && wget -q https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/${FILE} \
    && dpkg -i ${FILE} || apt-get install -yf \
    && rm -f ${FILE}

# ── frappe user ───────────────────────────────────────────────────────────────
RUN groupadd -g 1000 frappe \
    && useradd --no-log-init -r -m -u 1000 -g 1000 -G sudo frappe \
    && echo "frappe ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# ── bench CLI ────────────────────────────────────────────────────────────────
RUN pip3 install frappe-bench --break-system-packages

USER frappe
WORKDIR /home/frappe

# ── Initialise Frappe v16 bench ───────────────────────────────────────────────
RUN bench init \
    --skip-redis-config-generation \
    --frappe-branch version-16 \
    /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# ── Get our custom app ── (bust cache when app code changes) ─────────────────
# cache-bust: session auth fallback 2026-03-27
RUN bench get-app https://github.com/akshayedzola/impact-os-ai-frappe --branch main

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY --chown=frappe:frappe docker-entrypoint.sh /home/frappe/docker-entrypoint.sh
RUN chmod +x /home/frappe/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/home/frappe/docker-entrypoint.sh"]
