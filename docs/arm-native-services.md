# ARM64 native services (ANAL-224)

Android 17's native-only service launcher, `zygote_next`, does not initialize
ART or NativeBridge. Advertising `arm64-v8a` for ordinary translated apps does
not make that launcher capable of loading ARM64 libraries on x86_64. This doc
covers what OpenBook's framework patch does about it, its limits, and how to
test it. The bridge itself is in [`digitalis.md`](digitalis.md).

## The problem

An ARM64 app can declare a native-only service (`nativeService`, no Java
class). Android 17 starts it in an x86_64 child, which then tries to `dlopen`
the app's ARM64 library and aborts with
`EM_AARCH64 (183) instead of EM_X86_64 (62)`.

Chromium 158 (seen with 158.0.8111.0 on the G14) selects its native-only
renderer service on such a device. Chromium's secondary-ABI check compares
bitness, so it does not detect ARM64-on-x86_64 translation. When the child
dies, Android's shared process-start worker waits for a socket the dead child
never opens, and other apps' starts (Browser2 and OmaLauncher on the G14)
queue behind it: repeated crashes and a storm of connection-refused retries.

## The fix

`aosp/patches/frameworks/base/0010-OPENBOOK-native-services-require-host-ABI.patch`
changes three files:

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

**Why an OS alias.** Chromium 158's own immediate fallback is between native
services with and without an app zygote (it keeps the service class family and
changes the zygote suffix); it does **not** choose the managed service on a
failed bind. So the alias is needed for an unmodified APK. It is keyed by two
exact service class names and matching declarations inside the same package,
not by a general assumption that any native service has a Java class. An
absent, disabled or incompatible managed declaration fails closed.

ARM64 stays advertised. The translator, kernel, SELinux policy and browser
APK are unchanged. Host-ISA native services stay eligible.

## Limits

- This gives Chromium compatibility through its declared managed renderer.
  An ARM64 app with other native-only services and no supported fallback
  still can't run those services.
- Translation inside the native framework is separate work.
- ARMv7 is not advertised by this 64-bit product. The bridge's instruction and
  signal differences and its per-app limits still apply
  ([`COMPAT-MATRIX.md`](COMPAT-MATRIX.md)).

## Test

`scripts/compat/native-service/build.sh` builds an ARM64-only test APK with the
compatibility SDK/NDK (`docs/compat-harness.md`). Manifest resources come from
the candidate image's `framework-res.apk`: the public SDK still uses a staging
ID for `nativeService`, which the image would silently ignore, so the fixture
checks the resolved `FLAG_NATIVE_SERVICE` before testing. It then:

- attempts a native-only bind and requires rejection within one second;
- binds an isolated managed service and verifies a result computed by ARM64 JNI
  through Binder (its native-only service deliberately has no Java class);
- checks that a matching alias executes translated JNI and preserves the
  original callback component, that a fallback which would drop a permission is
  refused, and that an x86_64 native service stays eligible.

`PolicyProbe` runs against the image's own `services.jar` using `app_process`:
it checks 27 access/ABI conditions, including direct native-zygote APIs
rejecting ARM before connecting.

`scripts/compat/native-service/run-qemu.py` uses a disposable reflink of an
installed disk, never a laptop. `--baseline` shows an image without the patch
accepting the unsupported bind. Without that flag it repeats the probe three
times, installs an operator-supplied ARM64 Chromium APK, and checks three local
pages through DevTools: JavaScript, canvas pixels, and unrelated Settings
starts. It requires Chromium's managed-service alias to appear in the log, a
managed isolated renderer to exist, and no ELF mismatch or zygote retry storm.
The DevTools checks need `websocket-client`. Browser setup flags stay inside
the disposable VM.

```bash
scripts/compat/native-service/build.sh
python3 -m venv .venv
.venv/bin/pip install websocket-client
.venv/bin/python scripts/compat/native-service/run-qemu.py \
  --harness scripts/ota/ota-qemu.py \
  --disk <installed disk image copy>.img \
  --vars <its OVMF vars>.vars \
  --out "$HOME/anybook/logs/installer/ota/<run>/compat" \
  --probe "$HOME/anybook/compat/out/native-service/native-fallback-arm64.apk" \
  --host-probe "$HOME/anybook/compat/out/native-service/native-fallback-x86_64.apk" \
  --legacy-probes "$HOME/anybook/compat/out/probes" \
  --chromium /path/to/licensed/chromium-arm64.apk
```

Don't infer browser compatibility from a successful bind or a surviving
browser process alone: the renderer must execute and render content. Before any
laptop update, the candidate must also pass the installed-disk OTA, broken-boot
rollback and interrupted-transfer cases in `scripts/ota/ota-qemu.py`.

## Sources (checked 2026-10-19)

The Android 17 `ActiveServices.java` fetched from upstream was byte-identical
to the pinned file before the patch. Chromium sources were read at
`158.0.8111.0`.

- [AOSP NativeZygoteProcess](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/core/java/android/os/NativeZygoteProcess.java)
- [AOSP native library loader](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/libs/native_activity_thread/src/library_loader.rs)
- [AOSP ActiveServices](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android17-release/services/core/java/com/android/server/am/ActiveServices.java)
- [Chromium's native-service selection](https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8111.0/content/public/android/java/src/org/chromium/content/browser/ChildProcessCreationParamsImpl.java): its secondary-ABI check compares bitness, so it does not detect ARM64-on-x86_64 translation.
- [Chromium's bind-failure fallback](https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8111.0/base/android/java/src/org/chromium/base/process_launcher/ChildProcessConnection.java)
- [Chromium fallback selection](https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8111.0/base/android/java/src/org/chromium/base/process_launcher/ChildConnectionAllocator.java): the fallback keeps the selected service class family and changes the zygote suffix.
