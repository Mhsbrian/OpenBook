# ANAL-201: Googlebook image review, GApps options and a typography prototype (2026-10-17)

The write-ups are `docs/googlebook-ui.md` and `docs/gapps.md`. This directory holds metadata, configuration values and screenshots. No Google APK, font or image file is committed.

**Images read:**
- Googlebook `ruby` `CL3B.260622.271.R1`.
- Google APIs Desktop (Preview) 37.1 `CLE3.260929.004` (sha1 `7d2d46be…`).
- OpenBook `anybook_g14` and `anybook_cf_x86_64_pc` from `main` (2026-10-17).

## Results

| Check | Result | File |
|---|---|---|
| Package inventory | Googlebook 248 APKs (66 overlays); Google APIs Desktop 146 (32); OpenBook G14 111 (19) | `inventory/*-packages.tsv` |
| Who replaces the platform UI | Googlebook: Pixel Launcher, SystemUITitan, SettingsGoogle, WallpaperPickerGoogle. Google APIs Desktop: AOSP Launcher3 `Quickstep`, AOSP SystemUI, Settings and Wallpapers, with the same GMS | `inventory/*-packages.tsv` |
| Signers | SystemUITitan and SettingsGoogle share `framework-res`'s platform certificate `87b95a0a…`. GMS, GSF, Play Store and Chrome use Google's own keys | `inventory/googlebook-ruby-signers.txt` |
| GMS packaging | GmsCore 26.22.43 (x86_64 + x86) inside APEX `com.google.android.gmssystem` on `/product`, with a 139-permission allowlist. The same APEX is in the Google APIs Desktop image | `inventory/googlebook-ruby-gms-apex.txt` |
| Overlay configuration | 1,099 Googlebook config values. Fonts `google-sans` / `google-sans-text`, circular icon mask, round icons, wallpaper dim 0, 20 pointer drawables | `inventory/googlebook-ruby-overlay-config.txt.gz` (plus OpenBook's and the SDK image's) |
| Fonts | 253 font files. Product: Google Sans and the 2 clock fonts are proprietary; Google Sans Flex is OFL. 42 OFL document-compatibility system fonts that OpenBook lacks | `inventory/googlebook-ruby-fonts.tsv` |
| UI properties | Googlebook `supports_background_blur=1`; the OpenBook G14 product doesn't set it | `inventory/*-ui-props.txt` |
| aconfig flags | Googlebook enables 2,371, OpenBook G14 2,186. On in Googlebook and off for us: 728, of which 510 are not declared in AOSP 17 and 218 are (128 in UI packages) | `flags/` |
| **Font prototype (Cuttlefish, Radeon 610M, gfxstream)** | Boot 17 s. After pushing the OFL fonts, our `fonts_customization.xml` (40 families) and the RRO: overlay enabled; `config_headlineFontFamily=google-sans`, `config_bodyFontFamily=google-sans-text`; Settings, captions, Quick Settings and all apps render in Google Sans / Flex. Empty crash buffer | `fonts-prototype/` |
| Google APIs Desktop 37.1 in the emulator | **Did not boot.** No `sys.boot_completed` after 11 min. From about 4 min in (the earliest line left after logcat rolled over), 27,165 `binder error: kill 509 (surfaceflinger) Async binder space running out while frozen` and 13,955 `BR_FAILED_REPLY` from the ranchu composer. Stopped; not pursued, because the offline inventory answered the question | `gapis-desktop-37.1/boot-failure.txt` |

## Files

- `inventory/`:
  - `googlebook-ruby-packages.tsv`, `gapis-desktop-37.1-packages.tsv`, `openbook-g14-packages.tsv`: partition, kind, path, package, version, targetSdk, ABIs, MiB, label, overlay target, isStatic, priority.
  - `*-overlay-config.txt.gz`: `overlay type/name [config] = value`. Only default, night, orientation and size qualifiers; only config-style entries; no UI copy.
  - `googlebook-ruby-fonts.tsv`: family, version, licence, and whether OpenBook has the file.
  - `googlebook-ruby-config-xml.txt`: names of the permission, sysconfig, default-permission and preferred-app XMLs.
  - `googlebook-ruby-ui-props.txt`, `openbook-g14-ui-props.txt`.
  - `googlebook-ruby-signers.txt`, `googlebook-ruby-gms-apex.txt`.
- `flags/`:
  - `googlebook-ruby-flags.txt.gz`, `openbook-g14-flags.txt.gz`: every boolean flag in each image's `etc/aconfig` storage, read with `scripts/aconfig-storage-dump.py`.
  - `googlebook-on-openbook-off.tsv`: flag, container, whether AOSP 17 declares it, and the `.aconfig` file.
- `fonts-prototype/`:
  - `cmp-*.png`: before | after at half size, for the desktop, settings, Quick Settings, notifications and all apps.
  - `cmp-quick-settings-crop.png`; `before-settings.png`, `after-settings.png` at full size.
  - `before-ui-state.txt`, `after-ui-state.txt`; `fonts_customization.xml` (generated); `font-source.txt` (google/fonts commit and sha256); `cf-boot.log`.
- `gapis-desktop-37.1/`: `boot-failure.txt`, `capture.log`.

## Commands

See `docs/googlebook-ui.md` § Reproduce. Tools:
- `scripts/gbos-inventory.py`, `scripts/overlay-values.py`, `scripts/aconfig-storage-dump.py`;
- `scripts/ui/{fonts-customization.py,font-prototype.sh,ui-shots.sh}`;
- `scripts/desktop-ref-emulator.sh` (now takes `REF_API=37.1`).
