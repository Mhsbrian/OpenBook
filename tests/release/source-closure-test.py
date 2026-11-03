#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""scripts/release/source-closure.py on a made-up repository: missing, excluded, comment-only and stale references."""
import os
import subprocess
import sys
import tempfile

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "release", "source-closure.py")
FILES = {
    "scripts/build.sh": "#!/bin/sh\n# see docs/howto.md\nexec \"$R/scripts/helper.sh\" tools/Dockerfile.x\n",
    "scripts/helper.sh": "#!/bin/sh\npython3 scripts/lib/mod.py\n",
    "scripts/lib/mod.py": '"""Uses device/tree/Board.mk only in prose."""\nopen("data/table.tsv")\n',
    "tools/Dockerfile.x": "FROM scratch\n",
    "data/table.tsv": "a\tb\n",
    "docs/howto.md": "how\n",
    "device/tree/Board.mk": "x := 1\n",
}


def run(repo, packed, excluded):
    with open(f"{repo}/files.txt", "w") as f:
        f.write("\n".join(packed) + "\n")
    with open(f"{repo}/excluded.txt", "w") as f:
        f.write("".join(f"{p}\t{why}\n" for p, why in excluded))
    r = subprocess.run([sys.executable, TOOL, repo, "HEAD", f"{repo}/files.txt", f"{repo}/excluded.txt"],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        for p, text in FILES.items():
            os.makedirs(os.path.dirname(f"{d}/{p}"), exist_ok=True)
            open(f"{d}/{p}", "w").write(text)
        g = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@invalid"]
        subprocess.run(g + ["init", "-q"], check=True)
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "t"], check=True)

        rc, out = run(d, ["scripts/build.sh", "tools/Dockerfile.x"], [])
        if rc != 1 or "MISSING   scripts/helper.sh" not in out:
            fails.append("a script it runs, left out, was not reported missing")
        if "comment   docs/howto.md" not in out:
            fails.append("a path named only in a comment was not reported as such")

        rc, out = run(d, ["scripts", "tools/Dockerfile.x"], [("data", "test data")])
        if rc != 0 or "excluded  data/table.tsv" not in out or "comment   device/tree/Board.mk" not in out:
            fails.append(f"a closed set with a reasoned exclusion failed: {out}")

        rc, out = run(d, ["scripts", "tools/Dockerfile.x", "data"], [("data", "test data")])
        if rc != 1 or "STALE" not in out:
            fails.append("an exclusion nothing refers to was not reported stale")
    for f in fails:
        print("FAIL", f)
    print("source-closure: " + ("ok" if not fails else f"{len(fails)} failures"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
