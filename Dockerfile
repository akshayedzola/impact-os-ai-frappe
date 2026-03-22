FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget sudo \
    mariadb-client redis-tools \
    wkhtmltopdf xvfb libfontconfig libxrender1 \
    build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Node 18 ───────────────────────────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn \
    && rm -rf /var/lib/apt/lists/*

# ── bench CLI ────────────────────────────────────────────────────────────────
RUN pip3 install frappe-bench

# ── frappe user ──────────────────────────────────────────────────────────────
RUN useradd -m -s /bin/bash frappe \
    && echo "frappe ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER frappe
WORKDIR /home/frappe

# ── Frappe bench (downloads Frappe v16 — cached layer) ───────────────────────
RUN bench init \
    --skip-redis-config-generation \
    --frappe-branch version-16 \
    /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# ── Install our custom app ────────────────────────────────────────────────────
RUN bench get-app https://github.com/akshayedzola/impact-os-ai-frappe --branch main

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY --chown=frappe:frappe docker-entrypoint.sh /home/frappe/docker-entrypoint.sh
RUN chmod +x /home/frappe/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/home/frappe/docker-entrypoint.sh"]
