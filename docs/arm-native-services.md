# ARM64 native services (ANAL-224)

Android 17's native-only service launcher, `zygote_next`, does not initialize
ART or NativeBridge. Advertising `arm64-v8a` for ordinary translated apps does
not make that launcher capable of loading ARM64 libraries on x86_64.

## Failure and correction

On the G14, Chromium 158.0.8111.0 selected its native-only renderer service.
The x86_64 child tried to `dlopen` ARM64 `libchrome.so` and aborted with
`EM_AARCH64 (183) instead of EM_X86_64 (62)`. Android's shared process-start
worker then waited for a socket the dead child would never open. Browser2 and
OmaLauncher queued behind it. The original ANAL-224 evidence captured 12
matching crashes and 131,976 connection-refused retries.

The framework patch changes three files:

- `NativeZygoteProcess.java` compares the requested library instruction set
  with the runtime's actual instruction set. Both direct process starts and
  child-zygote starts reject a mismatch before connecting or forking.
- `ActiveServices.java` rejects unsupported native-only service lookups before
  creating records, prewarming a native zygote, adding bindings or queueing
  process starts. Other apps can still start promptly.
- `NativeBridgeServiceFallback.java` validates a narrow compatibility mapping
  for Chromium's two native-only renderer components to its two existing
  managed renderer components. Their package, UID, process, ABI, permission,
  export/enable/direct-boot state and isolation/zygote flags must match. Android's
  existing component-alias contract preserves the original component in callbacks;
  the usual visibility, permission, app-op and user checks apply to the resulting
  service. The ARM64 JNI then loads through Digitalis/Berberis.

Chromium 158's own immediate fallback is between native services with and
without an app zygote; it does **not** choose the managed service on a failed
bind. The OS alias is therefore necessary for this unmodified APK. It is keyed
by two exact service class names and matching declarations inside the same
package, not by a general assumption that any native service has a Java class.
An absent, disabled or incompatible managed declaration fails closed.

ARM64 remains advertised. The translator, kernel, SELinux policy and browser
APK are unchanged. Host-ISA native services remain eligible.

This provides Chromium compatibility through its declared managed renderer.
An ARM64 application with other native-only services and no supported fallback
still cannot run those services. Translation inside the native framework
remains separate work. ARMv7 is not advertised by this 64-bit product; the
previous Digitalis instruction/signal and individual-app limitations remain.

## Reproduce

`scripts/compat/native-service/build.sh` builds an ARM64-only APK using the
existing compatibility SDK/NDK and the synced AOSP API jar. It attempts a
native-only bind, requires rejection within one second, then binds an isolated
managed service and verifies a result computed by ARM64 JNI through Binder.
Its native-only service deliberately has no Java class. Additional fixtures
verify a matching alias executes translated JNI and preserves the original
callback component, a fallback that would drop a permission is refused, and
an x86_64 native service remains eligible. `PolicyProbe` runs against the actual
image's `services.jar` using `app_process`: it checks 27 access/ABI conditions,
including direct native-zygote APIs rejecting ARM before connecting.

`scripts/compat/native-service/run-qemu.py` uses a disposable reflink of an
installed disk, never a laptop. Pass `--baseline` to demonstrate the old
image accepting the unsupported bind. Without that flag it repeats the probe
three times, installs an operator-supplied ARM64 Chromium APK, and checks
three local pages through DevTools: JavaScript, canvas pixels, and unrelated
Settings starts. It requires Chromium's managed-service alias to appear in the log, a managed
isolated renderer to exist, and no ELF mismatch or zygote retry storm. `websocket-client` is required for the DevTools checks. Browser setup
flags are confined to this disposable VM.

```bash
scripts/compat/native-service/build.sh
python3 -m venv .venv
.venv/bin/pip install websocket-client
.venv/bin/python scripts/compat/native-service/run-qemu.py \
  --harness "$HOME/anybook/ota/armfix1/scripts/ota/ota-qemu.py" \
  --disk "$HOME/anybook/installer/ota/armfix1/after-ab.img" \
  --vars "$HOME/anybook/installer/ota/armfix1/after-ab.vars" \
  --out "$HOME/anybook/logs/installer/ota/armfix1/compat-after" \
  --probe "$HOME/anybook/compat/out/native-service/native-fallback-arm64.apk" \
  --host-probe "$HOME/anybook/compat/out/native-service/native-fallback-x86_64.apk" \
  --legacy-probes "$HOME/anybook/compat/out/probes" \
  --chromium /path/to/licensed/chromium-arm64.apk
```

Do not infer functional browser compatibility from a successful bind or a
surviving browser process alone. The renderer must execute and render content.
Before any laptop update, the candidate must also pass the installed-disk OTA,
broken-boot rollback and interrupted-transfer cases in `scripts/ota/ota-qemu.py`.

## Primary source verification, 2026-10-19

The Android 17 `ActiveServices.java` fetched from upstream was byte-identical
to the pinned file before this patch. Chromium sources were fetched at the
exact installed version, `158.0.8111.0`.

- [AOSP NativeZygoteProcess](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/core/java/android/os/NativeZygoteProcess.java)
- [AOSP native library loader](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/libs/native_activity_thread/src/library_loader.rs)
- [AOSP ActiveServices](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/services/core/java/com/android/server/am/ActiveServices.java)
- [Chromium's native-service selection](https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8111.0/content/public/android/java/src/org/chromium/content/browser/ChildProcessCreationParamsImpl.java): its secondary-ABI check compares bitness, so it does not detect ARM64-on-x86_64 translation.
- [Chromium's bind-failure fallback](https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8111.0/base/android/java/src/org/chromium/base/process_launcher/ChildProcessConnection.java)

- [Chromium fallback selection](https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8111.0/base/android/java/src/org/chromium/base/process_launcher/ChildConnectionAllocator.java): the fallback retains the selected service class family and changes the zygote suffix.
