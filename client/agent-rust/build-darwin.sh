#!/bin/bash
# Build Rust agent for macOS (arm64)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"

mkdir -p "$DIST_DIR"
cd "$SCRIPT_DIR"

echo "Building for macOS arm64..."
cargo build --release --target aarch64-apple-darwin

cp target/aarch64-apple-darwin/release/cert-agent "$DIST_DIR/cert-agent-darwin-arm64"

echo "Binary saved to $DIST_DIR/cert-agent-darwin-arm64"
ls -lh "$DIST_DIR/cert-agent-darwin-arm64"