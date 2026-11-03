#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# The backend's host unit tests (no GPU needed; hardware tests stay ignored), in the same image, offline.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd); M=${ANYBOOK_HOME:-$HOME/anybook}/mesa
docker run --rm --network none -u "$(id -u):$(id -g)" -e CARGO_HOME=/a/cargo -e NV_RM_DRIVER_VERSION=615.78.08 \
  -v "$M/cargo:/a/cargo:ro" -v "$repo:/repo:ro" -v "$M/build:/a/build" anybook-mesa-android-rust sh -c \
  "HOME=/tmp cargo test --offline --locked --lib --target-dir /a/build/nvk-rm-clean-hosttest --manifest-path /repo/backend/Cargo.toml"
