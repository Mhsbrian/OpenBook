# Phase 3 on the laptop: reconstruct and adapt Google's release (ANAL-229, 2026-10-24)

The laptop can now turn Google's Googlebook release into the G14's OpenBook release by itself. The new
tool is `openbook-adapt` (`device/anybook/common/updater/adapt/`): one static binary built from Go's
standard library only, plus the laptop's own `mkfs.erofs` and `fsck.erofs`. It runs the same code on the
host and on the laptop.

What it does:

1. **Reconstruct.** It reads the recovery zip the updater downloaded once, front to back, straight from
   the zip. It extracts Google's `system`, `system_ext`, `product` and `vbmeta`. Google's vbmeta
   signature must verify with Google's key (pinned by the layer), and every dm-verity root is recomputed.
2. **Adapt.** It re-applies the OpenBook layer to Google's new `system`. The layer is OpenBook's exact
   delta against the Google build a release was made from. OpenBook's own files are read from the running
   system and checked against the layer byte for byte. The carry rules are the host rebase's, ported
   exactly:
   - the three-way `build.prop` merge, with Python difflib's matcher;
   - the re-appended SELinux tails, with OpenBook Update's app-domain block derived again from the new
     policy;
   - the signer re-inserted before `</policy>`;
   - the policy hash recomputed.

   A path OpenBook changes that Google changed too stops it as **held**, with the reason.
3. **Rebuild and verify.** `mkfs.erofs` builds the system with the host's flags and content-derived
   UUID. Its inventory must equal the expected rows and its files the expected contents. Then come the
   AVB hash tree and footer, and the release vbmeta signed with the AVB test key, as today.

The same binary also writes a release's layer on the host (`layer`) and can write the next round's layer
into the adapted system (`--embed-layer`).

## Results

| Check | Where | Result |
|---|---|---|
| Unit tests (`go test`) | host | pass. They cover Python-compatible JSON/uuid5/re.escape, the merge cases of `rebase-google-build-test.py`, the block re-insertion and signer check, the domain substitution, the app-domain derivation, hash trees against a naive tree, the footer/vbmeta round trip and tamper detection, descriptor order, GPT/LP parsing and the fail-closed holds |
| Ports against the host tools (`host/parity.json`) | host | EROFS inventory identical on 7 real images. avbtool's footer and vbmeta byte-identical. App-domain derivation identical |
| Reconstruct Google 16658739 from its 7.8 GB zip | host 26 s, laptop 41 s | partitions identical to the host's staged stock. Google's signature and dm-verity roots verify |
| **Same build:** RB-20261023-03 from Google 16658739 plus its layer | host 21 s, **laptop 28 s** | **`system` `2e7b3425…` and `vbmeta` `d19d423c…` byte-identical to the installed release** |
| **Cross build:** a layer made on Google 16452207, applied to 16658739 | host 20 s, laptop 28 s | laptop output identical to the host's. Against RB-20261023-02: inventory (6,608 rows) and every file identical. The filesystem differs in 20 bytes, its UUID and checksum (`host/proofs.json`) |
| Production mode: the next round's layer embedded | host, laptop 28 s | laptop identical to host. The next round's layer equals the input layer, as a same-build adaptation should give |
| Updater engine: Google's real release, full size | laptop | **7.8 GB downloaded in 513–560 s and MD5-verified** (phase 1's open item) |
| Reproducible build (`build.sh --reproducible-check`) | host | two clean builds byte-identical (`adapter-build.json`, pinned official Go 1.27.2) |

The laptop runs (`laptop/`) used `adapt-device-test.sh` with the first build. The review fixes came after
that run. The pinned adapter (`090fe211…`) was run again on the laptop, with the same results:
`../2026-10-24-adapt-phase4/laptop/`. The laptop runs Everything ran as adb's shell user in one
temporary directory, removed at the end (`log.txt`). OpenBook's files came from the running system.
No partition, setting or app was touched.

For the engine's full-size download, the test listing named Google's real 16658739 release (Google's URL
and MD5) under the next build number. That is the only way to make the up-to-date laptop download it.
The listing stays private.

## Not done here

- Shipping `openbook-adapt` and the layer in the image, and the app's adaptation step. That is the next
  part of this issue and goes through a release.
- Phase 4: the payload, the per-laptop key and the install. The payload writer is written; its VM test is
  separate evidence.
- A real Google update after 16658739 (phase 5). The cross-build case above is the real
  16452207 → 16658739 step, adapted by the laptop.
