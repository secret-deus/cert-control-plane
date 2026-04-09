#!/bin/bash
# Build Rust agent for Linux x86_64
# Uses Docker if available, falls back to cross-compilation if toolchain is installed

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"

mkdir -p "$DIST_DIR"

# Check for cross-compiler
CROSS_CC=""
if command -v x86_64-unknown-linux-gnu-gcc &> /dev/null; then
    CROSS_CC="x86_64-unknown-linux-gnu-gcc"
elif command -v x86_64-linux-musl-gcc &> /dev/null; then
    CROSS_CC="x86_64-linux-musl-gcc"
fi

if [ -n "$CROSS_CC" ]; then
    echo "Building with cross-compiler: $CROSS_CC"
    cd "$SCRIPT_DIR"

    # Configure cargo for cross-compilation
    mkdir -p ~/.cargo
    cat >> ~/.cargo/config.toml << EOF
[target.x86_64-unknown-linux-gnu]
linker = "$CROSS_CC"
EOF

    cargo build --release --target x86_64-unknown-linux-gnu
    cp target/x86_64-unknown-linux-gnu/release/cert-agent "$DIST_DIR/cert-agent-linux-amd64"

elif command -v docker &> /dev/null; then
    echo "Building with Docker..."
    docker run --rm \
        -v "$SCRIPT_DIR:/src" \
        -w /src \
        rust:1.86-slim \
        sh -c "apt-get update && apt-get install -y musl-tools && cargo build --release --target x86_64-unknown-linux-musl"

    cp "$SCRIPT_DIR/target/x86_64-unknown-linux-musl/release/cert-agent" "$DIST_DIR/cert-agent-linux-amd64" 2>/dev/null || \
    cp "$SCRIPT_DIR/target/release/cert-agent" "$DIST_DIR/cert-agent-linux-amd64"
else
    echo "Error: Neither cross-compiler nor Docker available"
    echo "Install one of:"
    echo "  - Docker Desktop"
    echo "  - brew install messense/macos-cross-toolchains/x86_64-unknown-linux-gnu"
    exit 1
fi

echo "Binary saved to $DIST_DIR/cert-agent-linux-amd64"
ls -lh "$DIST_DIR/cert-agent-linux-amd64"
