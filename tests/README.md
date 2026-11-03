# Tests

| Level | What | Where | Runs |
|---|---|---|---|
| Fast host tests | Unit and fixture tests: no hardware, no images, no containers | `tests/` | `tests/run.sh`, by CI on every pull request |
| Component tests | Host tests that build a component in its container or need an image file: the install engine, bootsync, add-ons, live-init's disk logic, the release torrent | next to the tool they test, e.g. `scripts/installer/engine-test.sh`, `scripts/ota/bootsync-test.sh`, `scripts/installer/live-init-test.sh` | by the author of a change to that component |
| VM tests | The image in QEMU/KVM + OVMF: boot, install, update, rollback, graphics, audio and network | `scripts/installer/live-qemu.sh`, `scripts/installer/e2e-qemu.sh`, `scripts/ota/ota-qemu.py`, `scripts/audio-net-qemu.sh` and the other `*-qemu.*` harnesses | once per release, on the release build |

`CONTRIBUTING.md` ("Tests") says which level decides what. A test whose inputs haven't changed isn't run again.

Component and VM harnesses stay beside their tools for now: the build (`scripts/installer-image.sh`,
`scripts/graphics/make-gfx-check.sh`) and comments in `device/` call them by path. They move with the single build
entry point (M0.3, ANAL-343).

Results and logs go on the issue and into the evidence store (`$OPENBOOK_EVIDENCE`, default
`~/anybook/evidence/openbook`), never into Git.
