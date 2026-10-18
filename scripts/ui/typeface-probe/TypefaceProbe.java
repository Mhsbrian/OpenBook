// Measure text the way an Android app does, through Typeface.create(family) and Paint (ANAL-208).
// Run with app_process (scripts/ui/doc-fonts-typeface.sh builds and runs it). An app gets its font map from
// system_server; app_process has none, so this loads it the way system_server does at boot,
// Typeface.loadPreinstalledSystemFontMap() (hidden: /system/etc/font_fallback.xml plus
// /product/etc/fonts_customization.xml). Prints family, weight and the width of each string at 100 px with kerning
// and ligatures off: the strings doc-fonts-test.html measures.
import android.graphics.Paint;
import android.graphics.Typeface;

public class TypefaceProbe {
    static final String[] TEXTS = {"The quick brown fox jumps over the lazy dog 0123456789",
                                   "WAVE Ivy, fjord; mmm iii (42%) & @#?!"};

    public static void main(String[] args) throws Exception {
        Typeface.class.getDeclaredMethod("loadPreinstalledSystemFontMap").invoke(null);
        for (String family : args) {
            for (int weight : new int[] {400, 700}) {
                Typeface tf = Typeface.create(Typeface.create(family, Typeface.NORMAL), weight, false);
                Paint p = new Paint();
                p.setTypeface(tf);
                p.setTextSize(100f);
                // Unhinted, fractional advances, so the width is the font's own (no rounding per glyph).
                p.setSubpixelText(true);
                p.setLinearText(true);
                p.setFontFeatureSettings("'kern' 0, 'liga' 0, 'clig' 0, 'calt' 0");
                StringBuilder sb = new StringBuilder(family + "\t" + weight);
                for (String t : TEXTS) sb.append(String.format("\t%.3f", p.measureText(t)));
                System.out.println(sb);
            }
        }
    }
}
