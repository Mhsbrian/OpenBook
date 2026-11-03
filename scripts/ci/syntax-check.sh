#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Parse every tracked shell and Python script without running it: bash -n, and Python's compile().
#   scripts/ci/syntax-check.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
fail=0
while IFS= read -r -d '' f; do
  bash -n "$f" || { echo "shell syntax: $f"; fail=1; }
done < <(git ls-files -z '*.sh')
python3 - <<'PY' || fail=1
import subprocess, sys
files = subprocess.run(["git", "ls-files", "-z", "*.py"], check=True,
                       capture_output=True).stdout.decode().split("\0")
bad = 0
for name in filter(None, files):
    try:
        compile(open(name, "rb").read(), name, "exec")
    except SyntaxError as error:
        print(f"python syntax: {name}: {error}"); bad += 1
print(f"{len([f for f in files if f])} Python files parsed, {bad} with syntax errors")
sys.exit(1 if bad else 0)
PY
[ $fail -eq 0 ] && echo "syntax: ok"
exit $fail
