#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build Mesa's deqp-runner (MIT, https://gitlab.freedesktop.org/mesa/deqp-runner) as one static x86_64 musl binary
# for ANAL-177's graphics runs. It is the runner Mesa CI uses: it shards a dEQP case list over parallel deqp
# processes, restarts after a crash or a timeout, retries failures to find flakes, and compares the results with
# Mesa CI's expectation files (--baseline, --flakes, --skips). Static musl needs no bionic, so the same binary runs
# inside Android (as root, from the graphics add-on) and in the build host's pre-check container.
# The version is the one Mesa 26.2.5 pins (.gitlab-ci/container/build-deqp-runner.sh: DEQP_RUNNER_VERSION).
#
# usage: build-deqp-runner.sh          -> <data dir>/gfx-cts/bin/deqp-runner (+ deqp-runner.txt: version, sha256)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; G=$A/gfx-cts
VER=0.23.2; SHA=5dcd87423198d9f1af5dff4fd33bb852109da065
URL=https://gitlab.freedesktop.org/mesa/deqp-runner.git
S=$G/src/deqp-runner; mkdir -p "$G/src" "$G/bin" "$G/cargo"
[ -d "$S/.git" ] || git clone -q "$URL" "$S"
git -C "$S" cat-file -e "$SHA^{commit}" 2>/dev/null || git -C "$S" fetch -q origin tag "v$VER"
git -C "$S" checkout -q -f --detach "$SHA"
# rust:1-bookworm plus musl-tools (zstd-sys compiles C with musl-gcc); Cargo.lock pins every crate (--locked). The
# container runs as root to add the musl target and the package, then hands the build back to the caller's uid.
docker run --rm -e CARGO_HOME=/cargo -e CC_x86_64_unknown_linux_musl=musl-gcc -e U="$(id -u):$(id -g)" \
  -v "$G/cargo:/cargo" -v "$S:/src" -w /src rust:1-bookworm sh -c '
    set -e
    apt-get -qq update >/dev/null && apt-get -qq install -y musl-tools >/dev/null
    rustup target add x86_64-unknown-linux-musl >/dev/null 2>&1
    RUSTFLAGS="-C target-feature=+crt-static" cargo build --locked --release --target x86_64-unknown-linux-musl \
      --bin deqp-runner 2>&1 | tail -n 3
    rustc --version; cargo --version; chown -R "$U" /src/target /cargo'
install -m 0755 "$S/target/x86_64-unknown-linux-musl/release/deqp-runner" "$G/bin/deqp-runner"
{ echo "deqp-runner $VER ($SHA, $URL), MIT"
  echo "built: x86_64-unknown-linux-musl, static (crt-static), rust:1-bookworm"
  file -b "$G/bin/deqp-runner"
  sha256sum "$G/bin/deqp-runner" | cut -d' ' -f1; } | tee "$G/bin/deqp-runner.txt"
