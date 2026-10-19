# Persistent Googlebook USB diagnostics

2026-10-19, ANAL-228. The owner reported a black screen on the original live
candidate. It had VM serial diagnostics but no persistent ESP capture. The
failed physical image was preserved privately; no saved boot reports were found.

`validation.json` records the new logger's checks. The normal save-logs entry
was observed for 760.7 seconds through OVMF and emulated USB, without a serial
console. Its 600.2-second capture saved 228 files (17,533,446 bytes), with no
kernel overruns, failed saves or unsaved bytes. The logs include enforcing boot
completion, setup welcome, the known system-server SIGSEGV and the zram-related
`mmd_setup` abort. This is a logging pass, not a stable desktop pass.

The final candidate adds only the read-only TCGETS permission on the diagnostic
FIFO to remove harmless `ps`/`ls` isatty denials. The logger binary, collector
script, kernel and all non-vendor logical images are identical to the long-run
candidate. Its own 100.2-second test exercises the Mesa GL save-logs entry:
38 files, 3,149,136 bytes, enforcing mode, Mesa selected and no logger/FIFO
denials. Both tests preserve the source image and synthetic internal NVMe.

The native audit passes both stock baselines and the adapted hybrid with all
395 inputs unchanged. The original unadapted hybrid remains an expected policy
failure. The 13 compatibility guards, six live-image guards, UUID/FAT safety
checks and FAT filesystem check pass. The vendor label checks cover platform
defaults, APEX directories and the logger executable. No neverallow is disabled.

The final local image hash is
`19b9a9492f6b09bad04077378443d307f12ddd4a19f669e22486c88eb2b03f74`.
Generated recovery images, extracted contents, raw diagnostic streams and
software-TPM state remain local. The next G14 capture is required to diagnose
the physical black screen. Operation and reproduction: `docs/googlebook-live.md`.
