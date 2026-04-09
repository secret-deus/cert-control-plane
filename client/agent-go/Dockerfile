FROM golang:1.21 AS builder

WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY ./ ./

ARG TARGETOS=linux
ARG TARGETARCH=amd64

RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags="-s -w" -o /out/cert-agent ./cmd/cert-agent

FROM scratch AS artifact
COPY --from=builder /out/cert-agent /cert-agent
