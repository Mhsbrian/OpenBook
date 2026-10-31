# Release pipeline for openbook.page, 2026-10-31 (ANAL-320)

The release tooling run end to end on a real OpenBook live image: `openbook-live-20261018-anal191i.img`
(2,989,490,176 bytes, sha256 `abfddfca…8779`, `userdebug/test-keys`, no NVIDIA firmware). Nothing was uploaded or
published. Design and decisions: [`docs/RELEASE.md`](../../docs/RELEASE.md).

| What | Result | File |
|---|---|---|
| Compression on the real image: xz -6 / -9 / -9e, zstd -19 / -10 | xz -9 multi-threaded: **885,136,268 bytes (29.6 %)**, 92.9 s, decompresses in 3.4 s on 32 threads and 18.7 s on one | `compress-bench.log` |
| `make-release.sh` on the image | 104 s. The round trip matches the image's sha256, the torrent is 44,795 bytes (845 pieces of 1 MiB), and the signature verifies. `public: false`, blocked by `release_keys`, `user_build`, `source_offer` and `owner_approved` | `make-release.log`, `release-0.0.0-test.anal191i/` |
| `make-release.sh` on the 2026-10-30 G14 image, which carries NVIDIA's GSP firmware | refused: all three firmware names found, exit 1, no files written | `nvidia-refusal.txt` |
| `torrent-test.py`, against libtorrent 2.0.11 | **78/78.** Ten edge-case sizes and the real file: same v1 and v2 info hashes as libtorrent's own hybrid torrent, recheck 845/845, and one flipped byte fails exactly one piece | `torrent-test.log` |
| `swarm-test.sh`: nginx mirror, the `openbook-seeder` container and a libtorrent client on an isolated Docker network | **9/9.** The seeder refuses the unpublished release. Web seed only, through a 302: 885 MB in 2.0 s. Seeder only (Transmission 4.1.2 to libtorrent): 8.0 s. An earlier identical run took 3.3 s and 17.5 s. Both match the sha256. `swarm.json` counts 885,838,593 bytes uploaded, health passes, and the seeder's root and the releases folder are read-only | `swarm-test/` |
| `tracker-probe.py` | 3/3 default trackers answered a BEP 15 connect request (93 to 125 ms) | `tracker-probe.log` |
| `compose.example.yml` | `docker compose config -q` passes | |

Notes:
- `release-0.0.0-test.anal191i/` is signed with a **throwaway TEST-ONLY key** made for this run. It is not an
  OpenBook release key and must not be trusted. The `.img.xz` and `.torrent` are not in the repository. The
  release's GitHub mirror URL is a placeholder that does not exist.
- The seeder log shows that Transmission 4.1.2 ignores the torrent's v2 `file tree` and seeds it as v1. The
  libtorrent client, which uses both halves, downloaded from it without trouble. The DHT and "no network" errors in
  `seeder.log` come from the test network, which is `--internal` and has no route out.
- Not covered here: seeding from the Synology itself, peers reaching it through the router's port forward, and a
  real GitHub Releases web seed. Each needs the deployed stack or a published release.
