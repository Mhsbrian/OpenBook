#!/usr/bin/env bash
# Build quired_<version>_<arch>.deb for OpenBook's Linux environment (or any Debian or Ubuntu).
#
#   quire/linux-env/build-deb.sh OUTDIR [amd64|arm64]
#
# quired is a static Go binary (standard library only). dpkg-deb runs in a Debian container
# when the host has none.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src=$here/../quired
out=${1:?usage: build-deb.sh OUTDIR [amd64|arm64]}
arch=${2:-amd64}
mkdir -p "$out"
out=$(cd "$out" && pwd)
version=$(sed -n 's/^const version = "\(.*\)"/\1/p' "$src/main.go")
[ -n "$version" ] || { echo "no version in main.go" >&2; exit 1; }

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
root=$stage/quired_${version}_${arch}
install -d "$root/DEBIAN" "$root/usr/bin" "$root/usr/lib/systemd/system" "$root/usr/share/doc/quired"
(cd "$src" && CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -trimpath -ldflags='-s -w' -o "$root/usr/bin/quired" .)
install -m 0644 "$here/quired.service" "$root/usr/lib/systemd/system/quired.service"
sed -e "s/@VERSION@/$version/" -e "s/@ARCH@/$arch/" "$here/deb/control.in" > "$root/DEBIAN/control"
install -m 0755 "$here/deb/postinst" "$here/deb/prerm" "$here/deb/postrm" "$root/DEBIAN/"
printf 'quired is part of OpenBook: https://github.com/Mhsbrian/OpenBook\nLicence: see the repository.\n' > "$root/usr/share/doc/quired/README"

deb=quired_${version}_${arch}.deb
if command -v dpkg-deb >/dev/null; then
	dpkg-deb --root-owner-group --build "$root" "$out/$deb"
else
	docker run --rm -v "$stage:/stage" -v "$out:/out" debian:trixie-slim \
		dpkg-deb --root-owner-group --build "/stage/${root##*/}" "/out/$deb"
fi
echo "$out/$deb"
