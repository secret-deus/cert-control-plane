FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY agent/ /workspace/agent/
RUN pip install --no-cache-dir -e /workspace/agent

COPY tools/agent-smoke/edge-nginx.conf /etc/nginx/nginx.conf
COPY tools/agent-smoke/edge-entrypoint.sh /usr/local/bin/edge-entrypoint.sh

RUN chmod +x /usr/local/bin/edge-entrypoint.sh \
    && mkdir -p /etc/nginx/certs /var/lib/cert-agent

EXPOSE 9443

CMD ["/usr/local/bin/edge-entrypoint.sh"]
