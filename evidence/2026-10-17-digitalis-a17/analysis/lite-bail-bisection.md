# Bisecting a suspected JIT bug: the method, and why it pointed the wrong way (ANAL-200)

The first experiments said Fennec survived in `berberis.mode=interpret-only` and crashed in
`lite-translate-or-interpret`. We concluded the lite tier was at fault and bisected it with a debug knob
(`debug-lite-bail.patch`, not shipped). The knob reads `berberis.lite_bail` / `BERBERIS_LITE_BAIL`, a list of rules
that make the lite tier refuse instructions, which then run in the interpreter:
- `MASK/VALUE`: an instruction encoding class;
- `so:NAME[:LO-HI]`: file offsets of a mapping whose path contains NAME (it reads `/proc/self/maps`, with a cache);
- `!so:...`: never refuse inside that window;
- `noregmap`, `nodispatch`, `maxinsns:N`: region-level switches.

The search found:
- With `maxinsns:1`, bailing all loads/stores, all data-processing-immediate or all data-processing-register
  instructions "fixed" it. Bailing LDP/STP or SIMD did not.
- Bailing all of Fennec's own libraries (`so:/data/app/`) fixed it; bailing any single library did not. Bailing
  libxul and libmozglue together did.
- Offset bisection narrowed it to mozjemalloc's slot picker (libmozglue `0x76fac-0x77448`, `bisect-mozglue.log`) and
  to pref_SetPref and Gecko's HashString (libxul `0x2b732bc-0x2b73748`, `bisect-xul.log`). In both, each half was
  "needed".
- A differential test of variable shifts, rotates and the exact mozjemalloc sequence found nothing: every tier
  matched the reference.

Then interpret-only crashed too, with the release translator, the original flags and cleared app data. Every "fix"
above had only made execution slower, so the crash came after the 20–25 s check. The app data each run left behind
(`fennec-try.sh` did not clear it at first) changed how long startup took. With `pm clear` per run and longer waits,
every mode crashed at the same place. That tier-independence led to the real cause (`fennec-root-cause.md`).

Lessons for the next bisection:
- confirm that interpret-only really survives a long wait, from cleared data, several times, before suspecting the JIT;
- clear app data before every launch;
- a set of "fixes" that are unrelated but all slow is a timing signal, not a code signal.
