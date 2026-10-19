# Ruby framework on the OpenBook platform

Follow-up: `googlebook-live.md` adds the verified instruction-emulation lane,
bare-metal-module UEFI/USB packaging and boot-control entry contract. The
measurements below describe the initial KVM probe, before that follow-up.

2026-10-19, ANAL-228. This is the first local interoperability milestone after
the owner requested implementation. It uses the retained Ruby
`16452207_CL3B.260622.271.R1` research files, the existing OpenBook G14 product,
and the coherent `anybook-g14-gbos-16302624` kernel/module build. The installer
continues to offer Googlebook as **Not available yet**.

## Implemented boundary

`scripts/googlebook/compat-audit.py` checks stock Ruby, stock OpenBook, and their
mixed framework/vendor tuple with Android's native `checkvintf` and `secilc`.
It includes kernel release/configuration and **all preinstalled APEX manifests**:
47 APEXes on each side, with 9 Ruby and 12 OpenBook VINTF fragments. Module names
come from the APEX manifest rather than filenames. Android's
[VINTF manifest documentation](https://source.android.com/docs/core/architecture/vintf/objects)
(checked 2026-10-19) describes why vendor APEX fragments must be included.

The tool hashes policy, VINTF, APEX, build-property, kernel-config and tool inputs
before and after the checks. An input change fails the audit. Reports use path
aliases and always say `installable: false`. This is a supplied-tree audit, not
a cryptographic attestation that extracted trees came from a particular recovery.
The previous pinned raw/ZIP preflight and M0 extraction records remain separate.

| Tuple | VINTF, APEX and kernel | Strict SELinux compilation |
|---|---|---|
| Stock OpenBook | Pass | Pass |
| Stock Ruby | Pass | Pass |
| Ruby framework + unmodified OpenBook vendor | Pass | Fails on six debug/SwiftShader grants |
| Ruby framework + scoped probe adaptation | Pass | Pass |

Ruby is a production `user` framework; OpenBook's current vendor is `userdebug`.
The adaptation removes six exact grants in four statements: system_server's
SwiftShader execmem access, HAL test socket access to `su`, and debug tracing
file access. The count-checked profile rejects changed inputs instead of applying
a fuzzy substitution. Two additional rules permit the diagnostic process and
init to use the VM serial port. **Neverallow checks stay enabled and SELinux
stays enforcing.** These are pinned probe policies, not a generic vendor ABI.
A dedicated production vendor build should replace the reductions before release.

## Local VM assembly

`scripts/googlebook/hybrid-probe.py` requires successful baseline and adapted
audit results and checks their recorded input hashes again. It recompiles the
audited policy with strict checks into a private copy of the OpenBook vendor.
It rebuilds that vendor's EROFS using Android ownership/capability configuration
and file contexts. The CIL fallback and precompiled policy contain the same
adaptation; precompiled-policy identity files match the retained Ruby framework.

The VM's new GPT disk contains unchanged Ruby `system`, `system_ext` and
`product` logical images, OpenBook vendor, and matched G14 kernel/module images.
A local test-key AVB root covers their descriptors; this is an unlocked/orange
experiment, **not Google's original trust chain**. The OpenBook encrypted-data
fstab is retained. The stock recovery and original product trees are not changed.

The wrapper exposes only `/dev/kvm`, mounts source data read-only and limits
writes to the installer work area. QEMU has no network or physical disk. Its
guest writes use a disposable snapshot. The process is bounded, terminated and
reaped before the script returns. The output schema is deliberately distinct
from an install source, and the builder accepts only a new output directory.

## Measured progress and limits

The KVM experiment on the **Ryzen 9 7950X (Zen 4)** reaches first-stage mounts,
loads the matched G14 vendor modules successfully, loads enforcing SELinux,
starts software KeyMint/Gatekeeper and keystore2, initializes encrypted
userdata, and starts zygote. This passes the previous stock-Ruby startup stall
at keystore2/Trusty/GSC. It does not establish credential enrollment, key security
or persistence across reboots.

Zygote and boot animation then receive `SIGILL`. Both tombstone offsets decode
to **VEX `vpdpwssd` (AVX-VNNI)**: `libcrypto_httpengine.so+0xc7d3f` during
zygote's HTTP-engine ML-KEM self-test, and `libz.so+0x11145` during boot
animation's Adler-32 calculation. The standalone `vnni-probe.c` confirms that
this exact encoding traps on the 7950X and CPUID does not advertise AVX-VNNI.
AVX512-VNNI support does not imply support for this VEX encoding.

No completed Android boot or desktop is claimed. There are also unresolved denials involving Gatekeeper's
shared-secret service and the vendor boot patch-level property. These must be
reconciled through the service/property design; adding broad allows would
conflict with Ruby's neverallow rules. Uprobe loading and stock board services
produce additional errors that need independent triage.

The G14's HX 370 is **Zen 5**, not the KVM host. Its retained inventory includes
`avx_vnni`; the 7950X host does not. That is a concrete ISA difference, not proof
that these crashes disappear on the G14. See
`evidence/2026-10-16-ga403wr-inventory/cpu-isa-summary.txt`.

Local images, extracted APEXes and compiled policy stay outside the repository.
Only scripts, profiles, diagnostic metadata and logs are delivered. This
research milestone does not resolve deployment/redistribution rights. No USB,
internal disk, installed laptop OS or firmware was updated.

## Reproduction

Use an existing built G14 product and Android host tools; no new AOSP build or
download is required. Reserve at least 30 GiB scratch space, 8 GiB guest RAM
plus host memory, and four vCPUs. `RUBY` is the retained `gbos-unpack.sh` output;
`PRODUCT` is the G14 PRODUCT_OUT; `KERNEL` is its matched kernel dist; `TOOLS`
is AOSP's `out/host/linux-x86/bin`. Output directories must not exist.

```sh
python3 scripts/googlebook/compat-test.py -v
python3 scripts/googlebook/compat-audit.py \
  --ruby "$RUBY" --product "$PRODUCT" --kernel "$KERNEL" --tools "$TOOLS" \
  --out "$AUDIT"

# AUDIT and PROBE must be in the wrapper's writable installer workspace.
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/hybrid-probe.py" \
  --ruby "$RUBY" --product "$PRODUCT" --kernel "$KERNEL" --tools "$TOOLS" \
  --audit "$AUDIT" --key "$AOSP/external/avb/test/data/testkey_rsa4096.pem" \
  --out "$PROBE" --timeout 90
```

The audit exits nonzero if a required baseline/adapted check fails. The raw mixed
policy failure is an expected negative control. The probe's successful process
exit means its observation completed; read `result.json` and `serial.log` for
boot progress. Neither exit code authorizes installation.

## Next gates

1. Establish an AVX-VNNI-capable execution baseline for the unmodified framework.
   The failing instructions are now identified. Keep Zen 4, emulated CPU and
   HX 370 results separate; do not disable cryptographic self-tests.
2. Resolve the shared-secret/patch-level integration and verify PIN enrollment,
   reboot/unlock and key behavior under enforcing policy.
3. Reach a repeatable VM desktop, then test the Ruby framework with the Radeon
   890M stack on an explicitly approved external device.
4. Only then add the recovery source adapter, transactional writer, rollback
   tests and installer availability gate described in `googlebook-image-base.md`.

Actual checks, command output, image readback hashes, crash instruction identities
and the final 90-second VM serial log are in
`evidence/2026-10-19-googlebook-bringup/`. No screenshot is presented as desktop
evidence because the framework did not complete boot.
