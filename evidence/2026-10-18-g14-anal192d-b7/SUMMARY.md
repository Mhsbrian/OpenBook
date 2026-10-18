# ANAL-208 (B7): document fonts on the G14, from the owner's `anal192d` session (2026-10-18)

**Source:** the build host's read-only copy of the stick, `~/anybook/installer/g14/stick-20261018T123221Z/`, and the image file `~/anybook/installer/out/openbook-live-20261018-anal192d.img`. The stick itself was not touched.
- **Image:** `openbook-live-20261018-anal192d` (`main` `81578c1` + #83). It contains B7 (#78).
- **Boots:**
  - **A:** the default "OpenBook" boot, enforcing, about 11:00–11:59Z. Its logcat was persisted to `live-001/prior/`.
  - **B:** "save logs" (`live-001/`), permissive.
  - **C:** "ARM apps check" (`live-002/`), permissive.
- **B7's step on that stick was optional:** a photo of a `data:` page in the browser. The owner has posted no photos.

## Results

| Check | Result | File |
|---|---|---|
| B7 is in the image | `product_a` and `system_a`, extracted from the image, match the image manifest's sha256. Their B7 files match `81578c1` byte for byte: all 20 fonts in `/product/fonts` (B1's 3, B7's 17), `fonts_customization.xml`, and `/system/etc/fonts.xml`, which is the generator's output on the `frameworks/base` pin. `NOTICE.xml.gz` has all 7 B7 copyright lines | `image-check.txt` |
| The zygote reads B7's `fonts.xml` on the laptop | At every boot it loads `/system/etc/fonts.xml`, whose B7 families point at `../../product/fonts/`. The relative paths cause no warnings | `log-lines.txt` |
| Font errors | None in any boot: 0 warnings or errors from `SystemFonts`, `FontListParser`, `FontCustomizationParser`, `Typeface` or `FontManagerService`. No line names a B7 font file, and no SELinux denial names a font file. The 40 `TypefaceCache: MISS` lines from SystemUI and the wallpaper picker are first lookups, not errors | `log-lines.txt` |
| **The browser on the laptop** | Boot A opened WebView Shell three times (11:01:49 for 2 s, 11:05:58–11:07:14, 11:07:39–11:14:49). Pages: YouTube, a Cloudflare challenge, ad-served pages, the Aurora Store pages. No browser or renderer crash, and no line from those processes about fonts. The sandboxed renderers ran under enforcing with no font denial, so they could read the system fonts | `log-lines.txt` |
| **Arial, Times New Roman, Courier New, Georgia, Comic Sans MS on screen** | **Not shown.** No photo, and none of the session's screenshots shows the browser. The logs can't show which font a page drew; WebView doesn't log that | — |

**Not B7:** WebView's GPU thread logged 36 WebGL `GL_INVALID_OPERATION` errors (`glFramebufferTexture2DMultisample`, `glReadPixels`) between 11:06 and 11:14, on YouTube and the later pages. That is for the graphics work (ANAL-177).

## Open

- The photo of B7's `data:` page carries over to the `anal192e` checklist unchanged.

## Commands

```bash
W=~/anybook/b7/anal192d; IMG=~/anybook/installer/out/openbook-live-20261018-anal192d.img; B=~/anybook/aosp/src/out/host/linux-x86/bin
scripts/gpt-list.py $IMG                                    # super: start 946176, 2793472 sectors
dd if=$IMG of=$W/super.img bs=512 skip=946176 count=2793472
$B/lpdump $W/super.img                                      # product_a at super sector 1624064 (605824), system_a at 2048 (1361680)
dd if=$W/super.img of=$W/product_a.img bs=512 skip=1624064 count=605824
dd if=$W/super.img of=$W/system_a.img bs=512 skip=2048 count=1361680
$B/fsck.erofs --extract=$W/p $W/product_a.img; $B/fsck.erofs --extract=$W/s $W/system_a.img
cat live-001/prior/misc/logd/logcat.{16..1} live-001/prior/misc/logd/logcat > bootA-logcat.txt   # oldest first
```
