#!/usr/bin/env bash
# Download the public ci.android.com reference artifacts of a GKI kernel build into ~/anybook/kernel/ci/BID,
# for comparison with a local Kleaf build. These are GPL kernel build outputs from AOSP CI (no Google apps).
# The build ID is the -ab<N> suffix of the kernel release string, e.g. 6.18.21-android17-5-g3938c8d97142-ab16302624.
#
# usage: kernel-fetch-ci.sh BID [CI_TARGET]   (CI_TARGET default kernel_x86_64)
set -euo pipefail
BID=$1; CT=${2:-kernel_x86_64}
O=${ANYBOOK_HOME:-$HOME/anybook}/kernel/ci/$BID; mkdir -p "$O/logs"
U=https://ci.android.com/builds/submitted/$BID/$CT/latest/raw
for f in manifest_$BID.xml BUILD_INFO gki-info.txt repo.prop kernel_x86_64_dot_config vmlinux.symvers \
         System.map modules.builtin abi_symbollist system_dlkm.modules.load bzImage logs/build.log; do
  [ -s "$O/$f" ] || curl -fsSL --retry 5 --retry-all-errors -o "$O/$f" "$U/$f"
done
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("branch", d["branch"], "repo-init-branch", d["repo-init-branch"])' "$O/BUILD_INFO"
grep kernel_release "$O/gki-info.txt"
( cd "$O" && sha256sum bzImage kernel_x86_64_dot_config )
