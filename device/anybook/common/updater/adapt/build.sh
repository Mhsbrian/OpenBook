#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build openbook-adapt for the laptop: one static x86-64 binary (no cgo, no dependencies outside Go's
# standard library) with the pinned official Go toolchain, unit tests first. --reproducible-check builds
# twice from clean caches and requires identical bytes. Writes OUT/openbook-adapt and OUT/build.json.
#
# usage: build.sh OUT [--reproducible-check]
set -euo pipefail
OUT=$1 CHECK=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
GO_VERSION=go1.27.2
GO_SHA256=ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5   # go.dev/dl, linux-amd64
TOOLS=${OPENBOOK_TOOLCHAIN:-$HOME/anybook/toolchain}
GOROOT_DIR=$TOOLS/$GO_VERSION
if [ ! -x "$GOROOT_DIR/bin/go" ]; then
    mkdir -p "$TOOLS"
    tarball=$TOOLS/$GO_VERSION.linux-amd64.tar.gz
    if [ ! -f "$tarball" ]; then
        curl -fsSL --proto '=https' "https://go.dev/dl/$GO_VERSION.linux-amd64.tar.gz" -o "$tarball.part"
        echo "$GO_SHA256  $tarball.part" | sha256sum -c --quiet || { rm -f "$tarball.part"; exit 1; }
        mv "$tarball.part" "$tarball"
    fi
    echo "$GO_SHA256  $tarball" | sha256sum -c --quiet
    rm -rf "$GOROOT_DIR.tmp" && mkdir "$GOROOT_DIR.tmp" && tar -xzf "$tarball" -C "$GOROOT_DIR.tmp" --strip-components=1
    mv "$GOROOT_DIR.tmp" "$GOROOT_DIR"
fi
GO=$GOROOT_DIR/bin/go
"$GO" version | grep -qx "go version $GO_VERSION linux/amd64"
mkdir -p "$OUT"
build() {  # build DEST: from a fresh build and module cache, no network, no VCS stamp
    local cache; cache=$(mktemp -d "$OUT/.gocache.XXXXXX")
    (cd "$HERE" && env -i PATH=/usr/bin:/bin HOME="$cache" GOROOT="$GOROOT_DIR" GOCACHE="$cache/build" \
        GOMODCACHE="$cache/mod" GOFLAGS=-mod=mod GOTOOLCHAIN=local GOPROXY=off GOAMD64=v1 \
        CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
        "$GO" build -trimpath -buildvcs=false -ldflags="-s -w -buildid=" -o "$1" .)
    rm -rf "$cache"
}
cache=$(mktemp -d "$OUT/.gocache.XXXXXX")
(cd "$HERE" && env -i PATH=/usr/bin:/bin HOME="$cache" GOROOT="$GOROOT_DIR" GOCACHE="$cache/build" \
    GOTOOLCHAIN=local GOPROXY=off "$GO" vet ./... && env -i PATH=/usr/bin:/bin HOME="$cache" GOROOT="$GOROOT_DIR" \
    GOCACHE="$cache/build" GOTOOLCHAIN=local GOPROXY=off "$GO" test -count=1 ./...)
rm -rf "$cache"
build "$OUT/openbook-adapt"
sum=$(sha256sum "$OUT/openbook-adapt" | cut -d' ' -f1)
reproducible=null
if [ "$CHECK" = --reproducible-check ]; then
    build "$OUT/openbook-adapt.second"
    if cmp -s "$OUT/openbook-adapt" "$OUT/openbook-adapt.second"; then reproducible=true; else reproducible=false; fi
    rm -f "$OUT/openbook-adapt.second"
fi
src=$(cd "$HERE" && cat go.mod *.go | sha256sum | cut -d' ' -f1)
commit=$(git -C "$HERE" rev-parse HEAD 2>/dev/null || echo unknown)
clean=$( [ -z "$(git -C "$HERE" status --porcelain -- . 2>/dev/null)" ] && echo true || echo false)
cat > "$OUT/build.json" <<EOF
{
  "schema": "openbook-adapt-build/1",
  "sha256": "$sum",
  "go": "$GO_VERSION",
  "go_archive_sha256": "$GO_SHA256",
  "source_sha256": "$src",
  "commit": "$commit",
  "worktree_clean": $clean,
  "static": true,
  "reproducible_check": $reproducible
}
EOF
cat "$OUT/build.json"
[ "$reproducible" != false ]
