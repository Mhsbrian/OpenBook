#!/usr/bin/env python3
"""Compare exported-symbol CRCs (vmlinux.symvers) of two GKI builds, split by KMI symbol-list membership.

usage: kernel-kmi-diff.py OLD.symvers NEW.symvers [KMI_LIST]
  KMI_LIST  abi_symbollist from the OLD build's dist. A module built against OLD loads on NEW only if every
            symbol it imports still exists in NEW with the same CRC (CONFIG_MODVERSIONS).
"""
import sys


def load(p):
    return {f[1]: f[0] for f in (l.split("\t") for l in open(p)) if len(f) > 1}


def main(old_p, new_p, kmi_p=None):
    old, new = load(old_p), load(new_p)
    kmi = {l.strip() for l in open(kmi_p) if l.strip() and not l.startswith("[")} if kmi_p else set()
    both = old.keys() & new.keys()
    changed = sorted(k for k in both if old[k] != new[k])
    removed, added = sorted(old.keys() - new.keys()), sorted(new.keys() - old.keys())
    print(f"exports: old {len(old)}, new {len(new)}, common {len(both)}")
    print(f"CRC changed: {len(changed)}, removed: {len(removed)}, added: {len(added)}")
    if kmi:
        print(f"KMI list ({len(kmi)} symbols): CRC changed {sum(k in kmi for k in changed)}, removed {sum(k in kmi for k in removed)}")
    for title, xs in (("changed", changed), ("removed", removed), ("added", added)):
        for k in xs:
            print(f"{title}\t{'kmi' if k in kmi else '-'}\t{k}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
