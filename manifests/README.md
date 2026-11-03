# Source pins

What an OpenBook build is built from. Every revision here is an exact commit, so a build from a clean checkout
uses the same sources as the one before it.

| File | Pins | Read by |
|---|---|---|
| `aosp/manifest-pinned.xml.gz` | Every AOSP project (Android 17, `android17-release`, 1,084 projects), as `repo manifest -r` wrote it on 2026-10-15 | `scripts/aosp-patches.sh`, `scripts/ui/fonts-legacy-patch.sh` |
| `aosp/manifest-revision.txt` | The `platform/manifest` commit that pin came from | people |
| `kernel/gbos-16302624.xml` | The Kleaf workspace of the Googlebook OS kernel build 16302624 | `scripts/kernel-sync.sh` |
| `digitalis/digitalis-pinned.xml` | The DigitalisX64 projects of the ARM translation layer | `scripts/compat/digitalis/sync.sh` |

## Moving the AOSP pin

`scripts/aosp-sync.sh` writes a fresh `manifest-pinned.xml` and `manifest-revision.txt` to its log directory after
every tree sync. To move OpenBook to that tree, compress the manifest without a timestamp so its bytes depend only on
its content, then rebase the patch series in `aosp/patches/` on the new revisions:

```bash
gzip -9n < manifest-pinned.xml > manifests/aosp/manifest-pinned.xml.gz
cp manifest-revision.txt manifests/aosp/
```

A pin change changes the image. It goes in its own pull request, with the build and VM boot test for it.
