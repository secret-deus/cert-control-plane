FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY client/agent/ /workspace/agent/
RUN pip install --no-cache-dir -e /workspace/agent

COPY tools/real-scenario/nginx-matrix-entrypoint.sh /usr/local/bin/nginx-matrix-entrypoint.sh
RUN chmod +x /usr/local/bin/nginx-matrix-entrypoint.sh \
    && mkdir -p /var/lib/cert-agent /etc/nginx/matrix

CMD ["/usr/local/bin/nginx-matrix-entrypoint.sh"]
