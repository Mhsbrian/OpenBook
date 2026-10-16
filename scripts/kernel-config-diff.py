#!/usr/bin/env python3
"""Compare a locally built kernel .config with a shipped one, and explain where symbols come from.

usage: kernel-config-diff.py OURS SHIPPED DEFCONFIG KSRC [SYMBOL ...]  > report.md
  OURS, SHIPPED  full .config files (e.g. dist/dot_config and evidence/.../gbos-kernel-config.txt)
  DEFCONFIG      the defconfig the build started from (common/arch/x86/configs/gki_defconfig)
  KSRC           kernel source tree, scanned for Kconfig `select`/`imply`/`default` to attribute symbols
  SYMBOL         symbols to explain (without CONFIG_); defaults to pKVM/FRED plus the AMD enablement set

Report sections: (1) OURS vs SHIPPED, (2) SHIPPED vs DEFCONFIG (what stuck, what didn't, what is derived),
(3) per-symbol origin: explicit defconfig line, or which enabled Kconfig symbols select/imply it.
"""
import os, re, sys

DEFAULT_SYMS = [
    "PKVM_INTEL", "PKVM_X86", "X86_FRED", "KVM_INTEL", "KVM_AMD",
    # AMD platform enablement (docs/PLAN.md blocker 2)
    "DRM_AMDGPU", "DRM_AMD_DC", "PINCTRL_AMD", "AMD_PMC", "AMD_IOMMU", "X86_AMD_PSTATE",
    "CRYPTO_DEV_CCP", "AMD_SFH_HID", "I2C_DESIGNWARE_PLATFORM", "I2C_HID_ACPI",
    "SND_SOC_SOF_AMD_TOPLEVEL", "SND_SOC_AMD_ACP", "MT7921E", "MT7925E", "DRM_VIRTIO_GPU",
    "TRIM_UNUSED_KSYMS", "MODULE_SIG_PROTECT",
]
LINE = re.compile(r"^CONFIG_(\w+)=(.*)$")
UNSET = re.compile(r"^# CONFIG_(\w+) is not set$")


def load(path):
    """Return {symbol: value}; 'n' for `# ... is not set`, and line numbers for defconfig citations."""
    vals, lines = {}, {}
    for i, raw in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        raw = raw.rstrip("\n")
        if m := LINE.match(raw):
            vals[m[1]], lines[m[1]] = m[2], i
        elif m := UNSET.match(raw):
            vals[m[1]], lines[m[1]] = "n", i
    return vals, lines


def scan_kconfig(root):
    """Map symbol -> [(kind, owner, cond, file:line)] for select/imply, and symbol -> [defaults]."""
    rev, defaults = {}, {}
    head = re.compile(r"^\s*(?:menu)?config\s+(\w+)")
    rel = re.compile(r"^\s*(select|imply)\s+(\w+)(?:\s+if\s+(.+))?")
    dflt = re.compile(r"^\s*(?:default|def_bool|def_tristate)\s+(.+)")
    stop = re.compile(r"^\s*(choice|endchoice|menu|endmenu|if|endif|comment|source|mainmenu)\b")
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("Documentation", "out")]
        for f in files:
            if not f.startswith("Kconfig"):
                continue
            p = os.path.join(d, f)
            cur = None
            for i, raw in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                if m := head.match(raw):
                    cur = m[1]
                elif stop.match(raw):
                    cur = None
                elif cur and (m := rel.match(raw)):
                    rev.setdefault(m[2], []).append((m[1], cur, (m[3] or "").strip(), f"{os.path.relpath(p, root)}:{i}"))
                elif cur and (m := dflt.match(raw)):
                    defaults.setdefault(cur, []).append(m[1].strip())
    return rev, defaults


def fmt(v):
    return "unset" if v is None else ("n" if v == "n" else v)


def main(ours_p, shipped_p, defconfig_p, ksrc, syms):
    ours, _ = load(ours_p)
    shipped, _ = load(shipped_p)
    dfc, dfc_line = load(defconfig_p)
    out = []
    w = out.append

    keys = sorted(set(ours) | set(shipped))
    diff = [k for k in keys if ours.get(k) != shipped.get(k)]
    w("## 1. Our build vs shipped\n")
    w(f"- `{os.path.basename(ours_p)}`: {len(ours)} symbols; `{os.path.basename(shipped_p)}`: {len(shipped)} symbols.")
    w(f"- Symbols that differ: **{len(diff)}**.")
    if diff:
        w("\n| Symbol | Ours | Shipped |\n|---|---|---|")
        for k in diff:
            w(f"| `CONFIG_{k}` | {fmt(ours.get(k))} | {fmt(shipped.get(k))} |")
    w("")

    honored = [k for k in dfc if (shipped.get(k) or "n") == dfc[k]]
    dropped = [k for k in dfc if (shipped.get(k) or "n") != dfc[k]]
    derived_on = [k for k, v in shipped.items() if k not in dfc and v not in ("n", "")]
    w("## 2. Shipped config vs the defconfig\n")
    w(f"- `{os.path.basename(defconfig_p)}` sets {len(dfc)} symbols explicitly. {len(honored)} end up with that value in the shipped config.")
    w(f"- Defconfig lines that did **not** stick (dependency unmet, renamed, or overridden): **{len(dropped)}**.")
    if dropped:
        w("\n| Symbol | Defconfig asks | Shipped has |\n|---|---|---|")
        for k in sorted(dropped):
            w(f"| `CONFIG_{k}` | {dfc[k]} | {fmt(shipped.get(k))} |")
    w(f"- Enabled in the shipped config without being in the defconfig: {len(derived_on)} symbols. "
      "These come from Kconfig defaults and `select`, so a build from the defconfig alone reproduces them.\n")

    rev, defaults = scan_kconfig(ksrc)
    w("## 3. Where selected symbols come from\n")
    w("| Symbol | Shipped | Ours | Explicit in defconfig | Enabled selectors / implies (Kconfig) | Kconfig default |")
    w("|---|---|---|---|---|---|")
    for s in syms:
        exp = f"line {dfc_line[s]}: `{dfc[s]}`" if s in dfc else "no"
        by = [f"`{o}` ({k}{' if ' + c if c else ''}, `{loc}`)" for k, o, c, loc in rev.get(s, [])
              if shipped.get(o) not in (None, "n")]
        dv = "; ".join(f"`{x}`" for x in defaults.get(s, [])[:3]) or "none"
        w(f"| `CONFIG_{s}` | {fmt(shipped.get(s))} | {fmt(ours.get(s))} | {exp} | {'<br>'.join(by) or '-'} | {dv} |")
    print("\n".join(out))


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:5], sys.argv[5:] or DEFAULT_SYMS)
