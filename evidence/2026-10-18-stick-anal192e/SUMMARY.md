# The owner's stick `openbook-live-20261018-anal192e` (2026-10-18, the 120 Hz fix)

Built on the owner's request on ANAL-192 (12:30Z). It replaces `anal192d`. Recipe: `docs/installer.md` §13.9, in one lane-lock hold; the checklist is in §13.13. Everything here ran in QEMU/KVM + OVMF on image files, SELinux enforcing. **Nothing has run on the G14 yet.**

## What is on it
- **`main` `cb6099a`** (clean). Build log in `image/build-excerpt.txt`: 30 min 42 s, 51.3 GB peak. Kernel `6.18.21-android17-5-gfbfdd65b0fd1`; Vulkan 1.4 (`4210688`).
- **New since `anal192d`:**
  - #88 (ANAL-212): `config_defaultRefreshRate` 0, `config_defaultPeakRefreshRate` 1000, so there is no 60 fps cap;
  - #85 (ANAL-211): the bring-your-own-GApps installer step.
- **Not in it:**
  - #97 (ANAL-198: the `mediaserver` memfd rule for MediaPlayer under enforcing, and `amdgpu_firmware_info` in "save logs"). It merged after this build started;
  - the PRs still open at hand-off: #100, #101, #104.
- **Add-ons** (`image/addons.log`): the power check, the ARM apps check, and the graphics check `openbook-gfxcheck-anal192e` (`image/openbook-gfxcheck-anal192e-addon.json`).
- **sha256** `90631d0f5537cd36d7f52462cd8c8684ad3688072d9605e97ec4ac89a253f9c9` (`image/`), and `before-addons.sha256`.

## Results
| Run | Result | Here |
|---|---|---|
| Live stick matrix | **40/40** | `live-qemu/` |
| Refresh rate (#88's check) | **3/3**: config 0/1000, primary render max 1000, Settings scrolling at 75 Hz × 12 (the VM display's only mode) | `refresh-qemu/` |
| Wizard, 8 cases | **51/51** | `wizard-qemu/` |
| End to end | **79/79** | `e2e-qemu/` |
| Graphics check | 6/6 steps; `blur` 46 s | `addons-qemu/gfx-*` |
| ARM apps check | 5/5 verdicts | `addons-qemu/bridge-report.md` |
| Power check | vm 14/14, real 10/10 | `addons-qemu/power-*` |
| SELinux denials | 0 groups with an OpenBook type | `avc/anal192e.md` |
| `write-stick.sh --dry-run` | passes, nothing written | `image/write-stick-dry-run.log` (serial redacted) |

## Before this stick
The owner's `anal192d` session was copied read-only to `~/anybook/installer/g14/stick-20261018T123221Z/` (12:32Z) and routed to ANAL-176/178/179/191/198/200/202–208/212 and the coordinator.
