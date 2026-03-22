# ── Use Frappe's official bench image — all deps pre-installed ───────────────
FROM ghcr.io/frappe/bench:latest

# Switch to root to add Redis wait tool
USER root
RUN apt-get update && apt-get install -y --no-install-recommends netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe

# ── Initialise bench with Frappe v16 ─────────────────────────────────────────
RUN bench init \
    --skip-redis-config-generation \
    --frappe-branch version-16 \
    /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# ── Get our custom app ────────────────────────────────────────────────────────
RUN bench get-app https://github.com/akshayedzola/impact-os-ai-frappe --branch main

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY --chown=frappe:frappe docker-entrypoint.sh /home/frappe/docker-entrypoint.sh
RUN chmod +x /home/frappe/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/home/frappe/docker-entrypoint.sh"]
