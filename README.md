# AnyBook

AnyBook brings the Googlebook experience (Googlebook OS, Android 17 desktop) to x86_64 hardware Google doesn't ship. AMD Ryzen comes first, then other Intel parts, and NVIDIA later.

- `docs/PLAN.md`: the two-track plan, ranked blockers and milestones. Start here.
- `docs/RESEARCH.md`: verified facts, prior art and native-bridge licensing, with sources.
- `docs/STATUS.md`: Done / Evidence / Blocked / Next.
- `docs/BUILD.md`: reproducible steps. No host sudo needed; Docker and KVM required.
- `docs/HARDWARE.md`, `docs/COMPAT-MATRIX.md`
- `scripts/`: fetch, verify, unpack, ISA scan and QEMU boot tools. `tools/` holds the toolbox Dockerfiles.
- `evidence/`: logs and screenshots for each milestone.

No Google proprietary images, blobs or GMS go in this repo. Scripts work on images that each user downloads themselves.
