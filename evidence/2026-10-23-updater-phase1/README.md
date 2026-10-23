# On-laptop updater, phase 1: notice and download (ANAL-229, 2026-10-23)

`device/anybook/common/updater/openbook-updater` runs on the G14's own tools (mksh, toybox, awk, curl). It
checks Google's public release listing for this laptop's device and downloads a newer release, with
resume, a free-space reserve, HTTPS-only transfers and Google's MD5. Design: `docs/googlebook-on-device-updater.md`.

| Evidence | Result |
|---|---|
| Probe (read-only, G14 on RB-20261023-02) | native `curl` (HTTPS works to dl.google.com), `mkfs.erofs`, `fsck.erofs`, `lpdump`, awk, `md5sum`, update_engine services; no `avbtool`/`delta_generator`/`lpunpack`/`openssl`; mksh 32-bit arithmetic |
| `host-tests.txt` | 19/19 (host sh) |
| `on-laptop-tests.txt` (`openbook-updater-device-test.sh`) | 7/7 on the laptop: live listing check, a newer release downloaded and verified (empty date field), re-hash on repeat, MD5 mismatch refused, 32-bit-safe reserve, concurrent run refused, status. It used a temporary directory, removed afterwards; nothing was installed |
| ShellCheck 0.11.0 | clean at style level |

## Review

Two independent code reviews of the updater.

**First round:**

| Finding | Outcome |
|---|---|
| mksh 32-bit arithmetic broke byte counts (confirmed on the laptop: 5000000000/1024 → 688508) | all byte math in awk; regression test on the laptop |
| A partial download larger than the release stuck every run | discarded |
| The final move and the verification marker were unchecked | now checked |
| Downloads were never pruned | pruned |
| Redirects were not limited to HTTPS | `--proto =https --proto-redir =https` |
| Listing parsing was quadratic | one record per object |
| `--help` printed code lines | header only |
| The design doc was missing | written |
| "curl is not on Android" | disproven: `/system/bin/curl` on this image fetched the listing |

**Second round:**

| Finding | Outcome |
|---|---|
| Any failed resume deleted the partial | restart only on a refused range (curl 33/36, HTTP 416) |
| Tab-separated rows collapsed empty fields | ASCII unit separator |
| "Already verified" trusted the marker | re-hash before reporting verified |
| The size check could use a redirect's Content-Length | final response only |
| Pruning ran too early and kept installed builds | obsolete builds pruned at check time; others only after a verified download |
| Errors left stale keys | fresh state before the check |
| curl's progress meter went into the log | `-sS` |
| `--listing file://` failed | accepted |
| The host tests miss mksh | shell switch plus the committed on-laptop suite |

The on-laptop run also exposed what neither review predicted: mksh marks `exec 9>` descriptors
close-on-exec, so toybox `flock` never saw the lock. Fixed with a locking re-exec, verified on the laptop.
