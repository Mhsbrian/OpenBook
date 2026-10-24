# Root on the installed Googlebook (Ruby) image: survey and recommendation (ANAL-259)

Status as of 2026-10-24. This document surveys how to give the owner and the on-device
agent **reliable root** on the installed Ruby image of the G14 for development, **contained**
so the owner's day-to-day experience is unchanged, and recommends one mechanism.

Labels, as elsewhere in `docs/`:
- **CONFIRMED** — read in source/config we have locally, in a primary source, or in our own test output.
- **REPORTED** — upstream project docs, press, or user reports.
- **HYPOTHESIS** — our reasoning, not yet tested on hardware or in QEMU.

Nothing in this document has been run on the G14 or in QEMU yet. §9 and §10 are the
plans to do exactly that; their acceptance criteria gate the recommendation. The tools exist on the
build host (adb in `~/Android/Sdk/platform-tools`, QEMU through the project's Docker images); an earlier
revision wrongly said they were missing. This is
**build-time integration on the owner's own, privately built, never-published device**
(B Honey, ANAL-187, 2026-10-24), not an exploit of someone else's security. If the repo
or any image is ever published, this must be revisited (§11).

---

## 0. After approval (2026-10-24): two facts in §1 were wrong

B Honey approved §1 on 2026-10-24. Checking KernelSU's upstream sources before building showed that two of
its claims are wrong. The lab-helper floor is unaffected. **Decision (B Honey, 2026-10-24): interactive
per-app root is deferred, and the lab helper is the root path** (§0.3).

### 0.1 LKM mode loads from the boot ramdisk, not from our vendor module service (CONFIRMED)
KernelSU's LKM mode patches the ramdisk (`init_boot`, or `boot` on older devices) so that its own
`ksuinit` runs first and loads `kernelsu.ko`. It is not a module that `vendor.openbook.dlkm` loads later
(kernelsu.org/guide/installation.html; tiann/KernelSU PR #3570). Upstream v3.3.1 (2026-10-12) ships
`lkm-x86_64-android17-6.18_kernelsu.ko`, `ksuinit-x86_64` and `ksud-x86_64-linux-android` for our KMI.
Upstream lists AVD results for other KMIs only, so it is **not reported as tested on android17-6.18**.
So the release impact is the **boot ramdisk plus the manager app**, not vendor only. "Byte-identical GKI"
also no longer holds once ANAL-239's rebuilt kernel ships. The accurate claim is that KernelSU adds **no
further** kernel source change.

### 0.2 On x86_64 with our kernel, KernelSU needs a weakened kernel hardening (CONFIRMED, upstream)
Newer x86_64 kernels harden the syscall dispatcher: torvalds/linux `1e3ad78334a6`, 2024, in 6.9 and
backported to GKI. Ours has it. KernelSU's x86_64 support page says it then works only with one of two
measures:
- kernel source patches plus `syscall_hardening=off`, or
- the `KSU_X86_PATCH_SYSCALL_DISPATCHER` option, which `kernel/build-all-x64.sh` turns on for every
  upstream x86_64 LKM.

Upstream states that both mean "bypassing or weakening a mitigation designed to protect against
speculative execution vulnerabilities". It advises against them where side-channel security matters and
calls them intended for testing environments (kernelsu.org/guide/x86_64-support.html, tiann/KernelSU
`kernel/Kconfig`). The kernel-integrated fallback in §1 costs the same. So **no KernelSU variant comes
without a security cost on this laptop**. §1 did not say so, and the approval was given without that
information.

### 0.3 Decision (B Honey, 2026-10-24): defer interactive root
B Honey chose the recommended option on 2026-10-24.
- **The lab helper (option 3) is the root path** for the agent and all bring-up work (ANAL-238, 239, 257).
  It weakens nothing and covers every operation those issues need. It stays allow-listed, with no general
  `su`, and SELinux enforcing.
- **Interactive per-app root is deferred.** No KernelSU, Magisk or `su` is built for the laptop, and nothing
  from this issue enters a release. The §9 baseline and §10 prototype are not run, because they only matter
  if root for apps goes ahead.
- **When to revisit:** if a concrete app or task needs interactive root, open a new issue that starts from
  this section. The options at that point were:
  1. KernelSU, accepting the §0.2 cost knowingly, with QEMU first and the usual release approvals.
  2. Magisk. It is a userspace `su` daemon with a ramdisk `magiskinit` and a runtime sepolicy patch, and it
     does not patch kernel code (REPORTED). Its x86_64 / Android 17 status is unchecked, and its SELinux
     footprint (§5) still applies.

---

## 1. Recommendation (summary) — as approved; see §0 for corrections

A **two-tier** root path, because the agent's needs and the owner's needs are different and
the smallest mechanism that satisfies each is not the same one:

1. **Floor, kept regardless — the existing contained lab helper (option 3).**
   ANAL-238's `openbook_pc_setup` root vendor service, triggered by `setprop debug.openbook.*`,
   already gives the agent allow-listed root for the bring-up work (modules, sysfs, PCI power
   state, S0i3) with the narrowest, most auditable footprint and no general `su`
   (CONFIRMED: `device/anybook/common/pc/sepolicy/vendor/openbook_pc_setup.te`,
   `device/anybook/common/pc/init.openbook.rc`). It is already in review. **Nothing here
   replaces it;** everything below is additive, for the owner's *interactive, per-app* root.

2. **Primary for interactive per-app root — KernelSU, loaded as a signed kernel module (LKM mode).**
   KernelSU's per-app authorisation model and kernel-level `su` (no `su` file on disk) match the
   issue's "nothing visible by default, granted per request, easy to see and revoke" goal far
   better than Magisk, and LKM mode lets us keep the **byte-identical public GKI kernel** we worked
   to reproduce (`docs/kernel.md`) — no kernel source patch, no KMI change. It loads from
   `vendor_dlkm` exactly like our other modules, signed with our own build key, so it survives A/B
   updates because it is baked into each image we build. **Gate (§9):** prove in QEMU on the Ruby
   image that stock GKI 6.18's kprobe hooks are sufficient for KSU LKM. The kernel config
   prerequisites are present (§3); whether they are *sufficient* for a reliable LKM on this exact
   build is a **HYPOTHESIS** until QEMU shows it.

   **Fallback if LKM proves unreliable:** KernelSU integrated into the kernel we build, as a
   tracked KMI deviation on the nouveau precedent (ANAL-239 already carries a +33-export kernel
   deviation). More robust, but it costs the byte-identical GKI property and adds ongoing kernel
   maintenance, so it is the fallback, not the default.

3. **Not recommended as primary — Magisk.** Mature and its Zygisk+Shamiko hiding is the strongest
   against sophisticated checks, but its runtime `magiskpolicy` sepolicy patch adds a broad `magisk`
   domain, and Zygisk injects into every app's zygote. That is a larger, less auditable footprint
   than the issue's "nothing visible by default" goal, and it is a flashed boot/`init_boot` patch
   rather than a source-integrated module. Keep it documented as a **last-resort fallback** for a
   specific owner app that KernelSU's hide cannot satisfy, accepting the larger footprint.

The honest ceiling of all of this is in §12: simple root checks can be defeated; hardware-backed
attestation is already gone because the bootloader is unlocked, and **root changes nothing there** —
we will not pretend to defeat it.

---

## 2. What "root" and "hiding" mean here

Two distinct things the issue asks to get right together:

1. **A real root path** reachable over wireless adb for the owner and the agent: load/unload kernel
   modules, read PCI `power_state` and `dmesg`, write `/sys` and asus-wmi — the operations the
   installed `user` build's non-root `shell` cannot do (CONFIRMED on ANAL-238/257: `ro.debuggable=0`,
   user build, SELinux enforcing, no `su`).

2. **Containment** so the normal experience is unchanged — "hide" only in the daily-driver sense:
   apps that do *naive* root detection (looking for a `su` file, common root packages, a writable
   `/system`) keep working, and root is not something the owner trips over (no prompts, no warnings,
   nothing visible by default).

This is the ordinary posture of KernelSU's app profiles and Magisk's DenyList on any self-built
Android. It is **not** an attempt to deceive a third party about the device's integrity (§12).

---

## 3. Device and build facts that constrain the choice (CONFIRMED)

From the installed image and our reproduced build:

- **Installed Ruby on the G14 is a `user` build**, `ro.debuggable=0`, SELinux enforcing, no `su`,
  adb is the non-root `shell` user (ANAL-238/257, 2026-10-24). Dev/QEMU builds are `userdebug`, where
  `su` is already permissive (`docs/installer.md:161`, `docs/kernel.md:481`) — so the dev path already
  has root; the gap is the *installed user build* and *interactive per-app* root.
- **Kernel is the public GKI `android17-6.18` (6.18.21), byte-identical to Google's CI build**, built
  from `gki_defconfig` with **no** defconfig fragments, `trim_nonlisted_kmi=True`,
  `kmi_symbol_list_strict_mode=True` (`docs/kernel.md`). Any kernel *source* change breaks that
  property and must be tracked like the nouveau deviation.
- **Kernel config enablers for a KSU LKM are present** (CONFIRMED, `evidence/2026-10-15-m0/gbos-kernel-config.txt`):
  `CONFIG_KPROBES=y`, `CONFIG_HAVE_KPROBES_ON_FTRACE=y`, `CONFIG_KALLSYMS=y`, `CONFIG_KALLSYMS_ALL=y`,
  `CONFIG_OVERLAY_FS=y`, `CONFIG_MODULES=y`, `CONFIG_MODULE_SIG=y`, `CONFIG_SECURITY_SELINUX=y`,
  `CONFIG_SECURITY_SELINUX_DEVELOP=y`.
- **Module signing:** `CONFIG_MODULE_SIG_FORCE` is **not** set, and `CONFIG_MODULE_SIG_PROTECT=y`
  (CONFIRMED). We build and sign `vendor_dlkm` modules with our own key, so a KSU LKM signed by that
  key is fully trusted; a module signed by a different key counts as unsigned and cannot use protected
  symbols (the same mechanism that stops Google's GKI modules loading on our kernel, `docs/kernel.md`).
- **Verified boot is unlocked/orange with software KeyMint and no hardware attestation** — the port's
  design (`docs/PLAN.md:39`, `docs/nvidia.md`). Play Integrity hardware verdicts are already gone and
  "we will not work around that" (`docs/PLAN.md:133`).
- **Updates are A/B OTA** (ANAL-223): any root mechanism must either live in an image we rebuild each
  release (survives, because we bake it in) or re-apply itself post-install (fragile). This favours a
  module/image-integrated mechanism over a one-off flash.
- **An existing contained-root precedent:** the `openbook_pc_setup` domain and the non-exported
  `LabReceiver` (root/system-only, debuggable builds only) show the house style for a root control
  surface that no ordinary app can reach (`device/anybook/common/quire/.../LabReceiver.kt`).

---

## 4. Option 1 — KernelSU

**What it is (REPORTED, tiann/KernelSU + KernelSU-Next upstream):** a kernel-side root provider. `su`
is not a file on disk; an authorised process calls into the kernel (a `prctl` path) to gain root.
Authorisation is per-app (UID allowlist / app profiles) held by a manager app. It carries a built-in
hide: per-app "umount modules" unmounts systemless overlay modifications for a listed app, and there
is no `su`/`/sbin` path for a file scan to find.

**Two integration modes:**

- **LKM (loadable kernel module) — preferred here.** KernelSU is compiled as a `.ko`, signed with our
  build key, shipped in `vendor_dlkm`, and loaded early (we already run `vendor.openbook.dlkm` /
  `modprobe` at boot, `init.openbook.rc`). It uses kprobe-based hooks rather than compiled-in hooks.
  - *Fit with our build:* no kernel source patch and no KMI change. But see §0: the module is loaded by
    `ksuinit` from a patched ramdisk, not by our vendor module service, and on x86_64 it needs the
    weakened dispatcher hardening.
  - *Prerequisites:* `KPROBES`, `KALLSYMS_ALL`, `MODULES`, signing by our key — all CONFIRMED present
    (§3).
  - *Risk:* whether stock GKI 6.18's hook points are *sufficient* for a reliable KSU LKM (vs. a
    kernel that was built with KSU's manual hooks) is a **HYPOTHESIS** — the §9 QEMU gate.
- **Kernel-integrated — fallback.** KSU driver + hooks overlaid into the kernel source we build.
  More robust and the upstream-blessed path, but breaks byte-identity and adds to the KMI, so it is a
  **tracked deviation** (nouveau/ANAL-239 precedent) with ongoing maintenance cost.

**Hide (what it actually covers):** no `su` binary, no writable-system markers, systemless module mounts
hidden from listed apps → naive file/path/mount checks fail to find root. **Ceiling:** apps that probe
specifically for KernelSU (its manager package, known kernel-side signatures) can still detect it; that
is the honest limit of simple hiding (§12).

**SELinux:** KSU performs its domain work in a controlled way and global enforcing is preserved; the
QEMU gate (§9) must confirm **no new permissive domains and no unexpected denials** for an unauthorised
app. `SECURITY_SELINUX_DEVELOP=y` allows per-domain permissive but we require global enforcing to stay.

**A/B:** survives naturally — the `.ko` is part of each `vendor_dlkm` we build (ANAL-223).

**Verdict:** best match for the issue's goals **if the LKM gate passes**; otherwise the integrated
fallback.

---

## 5. Option 2 — Magisk

**What it is (REPORTED, topjohnwu/Magisk):** systemless root by patching the ramdisk (`init_boot`/`boot`)
with a preinit that sets up `magisk` and an overlay. DenyList + Zygisk hide root from listed apps; Zygisk
runs code in every app's zygote to do so.

- *Fit with our build:* we assemble the ramdisk, so a Magisk-patched `init_boot` can be baked in at
  build time and survives A/B because we rebuild it each release. But it is a **flashed prebuilt**
  (open source and reproducible, but not integrated into our source tree the way the lab helper and a
  KSU `.ko` are).
- *Hide:* DenyList + Zygisk + Shamiko is the **strongest** of the three against sophisticated checks.
- *SELinux:* Magisk applies a **runtime `magiskpolicy` patch** that adds a broad `magisk` domain and
  some rules. Global enforcing stays on, but this is a larger, less auditable policy change than the
  lab helper's narrow allow-rules or KSU's controlled transitions — in tension with "keep SELinux
  enforcing; a root path is not an excuse to go permissive."
- *Footprint:* Zygisk injecting into every zygote is more behavioural surface than "nothing visible by
  default" wants.

**Verdict:** keep as a **documented last-resort fallback** for a specific owner app that KSU's hide
cannot satisfy, accepting the larger footprint. Not the primary.

---

## 6. Option 3 — contained root service (the existing lab helper)

**What it is (CONFIRMED, in our tree, ANAL-238 PR #126, in review):** `openbook_pc_setup` runs as root
in its own narrow SELinux domain (`init_daemon_domain`), triggered by `setprop debug.openbook.*`, and
performs **allow-listed subcommands only** (dgpu-pm/report/ctl, module load via `vendor_modprobe`, sysfs
perms, kvm check). No general `su`. ANAL-257 extends it with the allow-listed lab actions (load/unload
`nouveau` and test modules, D0 hold, S0i3 report, timed s2idle), driven over adb by `setprop`.

- *Fit:* already built; smallest blast radius; fully auditable; narrowest SELinux footprint; enforcing.
- *A/B:* part of the vendor image we build.
- *Limit:* it is **not** general interactive root for the owner and cannot grant root to arbitrary apps
  the owner chooses — by design. It is enough for the agent's dev work, not for "an app the owner wants
  to run as root."

**Verdict:** keep as the **floor**, regardless of what we add for the owner. It is the agent's root path
and the safest one.

---

## 7. Why the two-tier recommendation

The agent's bring-up work (ANAL-238/239/257) needs root for a **fixed, known** set of operations — the
lab helper already covers that with the least risk, so there is no reason to route the agent through a
general `su`. The owner's ask is different: *interactive* root and the ability to grant it to **apps they
choose**, invisibly by default. KernelSU's per-app model is the right shape for that, and LKM mode keeps
our kernel discipline intact. Magisk would also work but at a cost to auditability and SELinux cleanliness
that the issue explicitly wants to avoid. So: lab helper for the agent (floor), KernelSU for the owner
(primary), Magisk only if a specific app forces it (fallback).

---

## 8. Owner control surface (task 4)

Design goals: nothing visible by default; root granted per request; a simple way to see and revoke what
has root. Mapped onto KernelSU + the house style:

- **Default off / invisible.** KSU ships with an **empty allowlist** — no app is authorised, so no app
  sees `su`, and there is no prompt or notification. The agent/shell UID is the only pre-authorised
  principal, and only on our userdebug vendor or behind a persist switch the owner sets once (the gating
  the lab helper already uses; adb requires authorisation, `ro.adb.secure=1`, ANAL-222).
- **Per-request grant.** The owner authorises a specific app through the KSU manager (or a thin wrapper
  surfaced in Quire/Settings, following the non-exported, root/system-only `LabReceiver` precedent so no
  ordinary app can reach it). Granting is explicit and per-UID.
- **See & revoke.** The KSU manager lists authorised apps with a toggle; the wrapper exposes the same
  list to the owner. Revoke is immediate (UID removed from the allowlist).
- **Hide per app.** For an app that does naive root checks, enable KSU's per-app "umount modules" so the
  app sees an unmodified system.

A one-screen owner view (authorised apps, last-used, revoke) is the deliverable for this tier; the
agent path stays the `setprop debug.openbook.*` lab helper and needs no UI.

---

## 9. Baseline measurement (task 2) — PLAN, not yet run

**Required before any root is added, to separate pre-existing unlocked-state effects from anything root
adds.** Not yet executed. These are the exact steps and acceptance criteria for the next adb session (after the §Rules pre-checks: no release
op on the laptop, nobody else on adb, owner warned).

Over wireless adb to `192.168.50.11` on the current `user` Ruby (read-only, no image write):

1. **App inventory:** `adb shell pm list packages -3` and `-s` → record the 262 packages; flag the owner's
   own apps.
2. **Which misbehave today:** for each owner app, launch and capture `logcat` for root/integrity/attestation
   errors; record any that refuse to start or degrade **before** any root. This is the set root must preserve.
3. **Play Integrity verdict today:** run the owner's existing integrity check (or a known client) and record
   the verdict (expected: hardware/STRONG already failing due to unlocked bootloader; BASIC/MEETS_BASIC is
   the interesting line). Record it as the pre-root baseline.
4. **Save** all of it under `evidence/<date>-root-baseline/` as the "what root must not break" reference.

Acceptance: a written baseline of (a) which owner apps misbehave pre-root and (b) today's integrity verdict.

---

## 10. QEMU prototype (task 3) — PLAN, not yet run

In QEMU on the Ruby image (`scripts/g14-qemu.sh` / `scripts/gbos-qemu-boot.sh`), **not** on the laptop:

1. Build the Ruby image with the chosen KSU LKM in `vendor_dlkm`, signed with our build key; load it from
   the existing dlkm init path.
2. Boot and verify:
   - **Root reachable:** an authorised principal gets `su`/uid 0.
   - **`su` not visible to a DenyList/profile-ed test app:** a test app with naive checks finds no root.
   - **SELinux still enforcing:** `getenforce` = Enforcing globally; **no new permissive domains**; no
     unexpected denials for an unauthorised app (compare against the pre-root `avc` baseline, `docs/adb-debug.md`).
   - **No boot regression:** boots to shell/UI on both slots; the lab helper and existing services unaffected.
3. If LKM is unreliable (hooks insufficient), repeat with the integrated-KSU fallback and record the KMI
   delta like ANAL-239.

Acceptance (the §1 gate): all four bullets pass in QEMU on the Ruby image before anything is proposed for the laptop.

---

## 11. Release impact and hand-off (task 5)

**Release impact: none** (decision, §0.3). The lab helper ships with ANAL-238/257, and this issue adds
nothing to any image. For a future revisit only:
- LKM path: **boot ramdisk + the manager app** (§0.1). No kernel source change, but on x86_64 the module
  patches the kernel's syscall dispatcher at runtime (§0.2).
- Integrated fallback: **kernel + vendor** — a tracked KMI deviation (nouveau precedent) plus the vendor
  pieces.

**Do not hold the combined ANAL-238/239/257 lab-helper vendor update for this issue** (§0.3). If the owner
later chooses an interactive-root option, it goes in its own Ruby release or the next combined one. Hand off with the usual approvals (ANAL-232): B Honey
approves the specific plan before build/test; a separate approval names the final image, operation and exact
device before any physical write; adb stays authorised; SELinux stays enforcing. The intake watch on the hub
(ANAL-232) is registered only when a prototype produces an image-affecting hand-off ready for review — not for
this survey, to avoid a duplicate/premature rule.

**Evidence to keep:** the §9 baseline, the §10 QEMU results, the containment proof (DenyList-ed app sees no
root; enforcing; no new denials), and the owner app list before/after.

---

## 12. What hiding can and cannot do (read this honestly)

- **Simple root checks** (looking for `su`, common root packages, writable system) **can** be kept from
  seeing root — KSU app profiles / Magisk DenyList. The majority of "won't run on a rooted phone" cases.
- **Play Integrity / hardware-backed attestation is a different thing, and it is already gone on this port
  regardless of root.** STRONG/hardware verdicts need a locked bootloader and green verified boot; we run
  unlocked/orange with software KeyMint and no hardware attestation (`docs/PLAN.md`, `docs/nvidia.md`). Apps
  that demand hardware attestation (some banking apps, HD DRM video, some anti-cheat) are already affected by
  the unlocked state — **root changes nothing there, and we will not pretend to defeat it.**
- **We do not bypass anti-cheat, fraud, or licensing to deceive a third party.** The aim is narrow and
  legitimate: keep the owner's own apps working on the owner's own rooted development laptop. Anything an app
  still refuses after basic hiding, we report honestly rather than escalate against.
- **KernelSU/Magisk are themselves detectable by apps that probe for them specifically.** Simple hiding has a
  ceiling; we state it rather than overclaim.
