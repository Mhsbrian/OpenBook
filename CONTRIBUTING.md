# Contributing to OpenBook

This is how OpenBook is built, reviewed and released. It applies to everyone, people and agents alike.

## What goes in this repository

Source that builds OpenBook, and the documentation needed to build, install and use it. Nothing else.

| In the repository | Never in the repository |
|---|---|
| Device tree and product configuration | Test output, logs, reports, screenshots, captures |
| AOSP patch series and their manifest pins | Hardware dumps, session notes, per-task write-ups |
| Kernel config fragments, patches, module lists | Disk images, payloads, archives |
| Mesa patches and build scripts | Keys, tokens, credentials |
| Installer, build and release tooling | Anything from one person's machine or network: IP addresses, serial numbers, account names |
| Automated tests and their small fixtures | Google images or anything extracted from them |
| Brand sources, user and developer docs | |

Test results and evidence go on the issue as attachments and into the maintainers' evidence store. A pull
request links to them; it doesn't contain them. `scripts/ci/check-hygiene.py` enforces this.

Build inputs are pinned in `manifests/` (the AOSP revision pin, kernel and Mesa sources), never in a results
folder.

## Layout

| Path | What it holds |
|---|---|
| `manifests/` | `repo` manifests and source pins: what AOSP, kernel and Mesa revisions a build uses |
| `device/` | Product and board configuration (`device/<vendor>/<product>`, AOSP layout) |
| `aosp/patches/<project>/` | Patch series applied on top of the pinned AOSP projects |
| `kernel/` | GKI config fragments, patches and vendor module lists for Kleaf |
| `mesa/` | Mesa patches and the Android build of radeonsi, RADV and NVK |
| `scripts/` | Build, image, installer and release tooling |
| `scripts/ci/` | What CI runs |
| `tests/` | Automated tests and fixtures |
| `assets/` | Brand sources: wallpapers, boot animation, sounds, icons |
| `docs/` | How to build, install and use OpenBook, and how it works |

## Pull requests

- **One feature or one fix per pull request.** A change that only records results, status or a session is not a
  pull request. Post it on the issue.
- **Title:** [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) form,
  `type(scope): summary`. Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `build`, `ci`, `test`, `chore`.
  Example: `feat(graphics): per-app NVIDIA GPU choice`.
- **Description:** what changes, why, how it was tested (commands and results), and any risk. Link the issue.
  Use the template.
- **Keep it reviewable.** Split large changes. An imported third-party tree goes in its own commit and says so.
- **Docs change with the code they describe.** `docs/STATUS.md` changes at release time, not in every pull request.
- **Merging:** CI green and one independent approving review, then squash-merge. Nothing is pushed to `main`
  directly and `main` is never force-pushed.
- **Commit identity:** a no-reply address only. Check `git log --format='%ae %ce'` before pushing.

## Tests

Each test runs once, at the level where it decides something. Don't rerun a test whose inputs haven't changed.

1. **CI, every pull request:** repository hygiene, script syntax, unit tests. Fast, no hardware.
2. **The author, before review:** the checks for what the change touches, such as a component build, its unit
   tests, or the VM test for that area. Put the commands and results in the pull request.
3. **The release, once per release:** on the release build itself, the VM boot, install, update and rollback
   suite, then a smoke test on the reference laptop. Results go on the release issue.

## Releases

- **Versions:** [SemVer](https://semver.org/), `MAJOR.MINOR.PATCH`, with `-preview.N` for developer previews.
  Tag `vX.Y.Z[-preview.N]` on `main`. A release branch exists only when a shipped release needs a fix.
- **A release is:** the tag, plus a GitHub release with the image, `SHA256SUMS`, its signature, the
  corresponding source archives (kernel GPL source included) and its section of `CHANGELOG.md`.
- **Changelog:** [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), written for people. Merged pull
  request titles are the input, not the text.
- **Built once,** from a clean checkout of the tag (`docs/BUILD.md`). `scripts/release/make-release.sh` then packages
  that image, with its checks, signatures and source offer; it doesn't build the OS.
- **Signing:** developer previews are `userdebug` builds with AOSP test keys, and say so. Public betas and
  later are `user` builds signed with OpenBook's release keys.

## Hardware safety

Tools that write to a disk take an explicit `/dev/disk/by-id/...` path and work on image files by default.
Nothing flashes, repartitions or wipes a disk, USB stick or laptop, writes a system image to one, or writes
firmware without the owner's approval of a request naming that exact image, operation and device. Installing
apps or temporary test files over adb doesn't count.
