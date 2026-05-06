FROM golang:1.21 AS builder

WORKDIR /src/agent-go
COPY client/agent-go/go.mod client/agent-go/go.sum ./
RUN go mod download
COPY client/agent-go/ ./

ARG TARGETOS=linux
ARG TARGETARCH

RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH:-amd64} \
    go build -trimpath -ldflags="-s -w" -o /out/cert-agent ./cmd/cert-agent

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out/cert-agent /usr/local/bin/cert-agent
COPY tools/agent-smoke/edge-nginx.conf /etc/nginx/nginx.conf
COPY tools/agent-smoke/edge-entrypoint.sh /usr/local/bin/edge-entrypoint.sh

RUN chmod +x /usr/local/bin/edge-entrypoint.sh /usr/local/bin/cert-agent \
    && mkdir -p /etc/nginx/certs /var/lib/cert-agent

EXPOSE 9443

CMD ["/usr/local/bin/edge-entrypoint.sh"]
