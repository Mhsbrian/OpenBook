# The installed G14 still showed 60 fps at 120 Hz: the composer's CTM (2026-10-18, 16:35–18:00Z)

- **Setup:** the installed `anal192e` (`main` with #88), measured over adb from the build host. The owner reported
  60 fps in testufo.com on Chrome and in moving around.
- **Doc:** `docs/graphics-amd.md`, "Second cause".

## What was measured, before any change

| File | What it shows |
|---|---|
| `timestats-chrome-ufo-8s.txt` | testufo.com in Chrome, 8 s. SurfaceFlinger at 120 Hz composed 480 frames: 477 missed, 470 of 478 present intervals 16 ms. RenderEngine took about 3 ms per frame |
| `chrome-layer-latency.txt` | Chrome's layer: 62 of 62 present intervals were 16.7 ms, each frame on screen about 28 ms after its desired present time |
| `timestats-settings-scroll.txt` | Settings scrolling: 315 of 315 intervals 16 ms. All content is affected, not only Chrome |
| `perfetto-summary.txt` | 6 s trace. The composer commits about 2.2 ms after a vblank, but its present fence waits 14 ms (`AsyncWaitForBuffersSwap`), so each flip lands two vblanks later |
| `kprobe-commit-path.txt` | amdgpu/DC for one flip: `dcn35_update_clocks` (the bandwidth step of a full update), about 4 ms idle, then programming just after the next vblank |
| `drm-atomic-debug.txt` | Every commit: "Disabling DRM plane" then "Enabling DRM plane" (`should_reset_plane`) |
| `kprobe-ctm-blobs.txt` | 62 CTM blob replacements for 62 atomic checks, IDs cycling 520/521…527/528. No commit took DC's fast path |
| `kprobe-idle-update-types.txt` | While idle, every commit is a full update. `amdgpu_dm_ips_status`: idle optimization 1, IPS never entered |

## The fix on the laptop, A/B with the same tool

`scripts/graphics/g14-flip-check.sh --scroll` scrolls Settings, takes 8 s of TimeStats, and runs 1.5 s of kprobes.
The patched composer was built out of band (`composer-build.txt`). An unpatched rebuild matches the installed binary
section for section, so the patched build differs from the installed one only by
`aosp/patches/external/drm_hwcomposer/0001`. It ran via `scripts/graphics/g14-composer-swap.sh`: a tmpfs bind mount,
no partition written.

| | Installed composer (`flip-check-installed-composer.txt`) | Patched composer (`flip-check-patched-composer.txt`) |
|---|---|---|
| Frames composed in 8 s | 481 | **961** |
| Missed frames | 490 | **0** |
| Present-to-present | 16 ms × 477, 8 ms × 1, 25 ms × 1 | **8 ms × 959** |
| DC update types, 1.5 s | full 91, fast 0 | **fast 181, full 0** |
| Planes re-added to the DC state | 182 | **0** |
| New CTM blobs | 91 | **0** |
| RenderEngine, average | 3.6 ms | 3.3 ms |

The panel scanned out at 120 Hz in both runs, and SurfaceFlinger's policy was [0, 1000] in both.

## Incident: one unplanned reboot (17:48Z)

The first version of `g14-composer-swap.sh` bind-mounted the binary from `/data/local/tmp`. `/data` is mounted
`nosuid`, so SELinux refused init's transition into the HAL domain:
`avc: denied { nosuid_transition } … scontext=u:r:init:s0 tcontext=u:r:hal_graphics_composer_default:s0`, followed by
`execute_no_trans`.

The composer could not start, and the system rebooted itself about a minute later. It came back on the installed
binary: the bind mount does not survive a reboot, and nothing on the disk had changed.

The script now:
- stages the binary on a fresh tmpfs mounted without `nosuid`;
- uses lazy unmounts (a plain `umount` fails while the composer has the file mapped);
- runs the restart and a 10 s check detached, so a cut adb session can't skip it. If the new composer is not running
  after 10 s, the check removes the bind mount, so init falls back to the installed binary.

That version was used for every later swap, with no further reboot.

## State left on the laptop

The patched composer stays bound until the next reboot (pid 10111 at 17:59Z). It reverts with
`scripts/graphics/g14-composer-swap.sh --revert` or with any reboot. The permanent fix arrives with the next image
or network update built from `main` with the patch.
