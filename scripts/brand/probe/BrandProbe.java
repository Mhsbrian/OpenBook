// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
//
// On-device checks for OpenBook's brand assets (ANAL-207). Runs as root through app_process, outside any app:
//   adb push brand-probe.jar /data/local/tmp/ && adb shell CLASSPATH=/data/local/tmp/brand-probe.jar \
//     app_process /system/bin BrandProbe <command> ...
// Commands:
//   pointers OUTDIR [SCALE]  render every system pointer icon the way system_server does (PointerIconCache: the
//                            context's theme plus the fill and stroke styles, PointerIcon.getLoadedSystemIcon), for
//                            all 6 fills x 3 strokes; writes PNGs and prints type, style, size and hotspot.
//   palette                  print the dynamic colours apps see now (android.R.color.system_*).
//   set-wallpaper FILE       set FILE as the home and lock screen wallpaper (WallpaperManager.setStream).
//   resinfo TYPE/NAME        which value a framework resource resolves to here (overlays included): its ID, and for
//                            an XML drawable the first pathData, for a bool or string the value.
// Screencap does not draw the pointer, so `pointers` is how the theme is seen on a device: the bitmaps come from the
// same framework code and the same resources (our overlay) as the real pointer.
import android.app.WallpaperManager;
import android.content.Context;
import android.content.res.Resources;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.os.Looper;
import android.view.ContextThemeWrapper;
import android.view.PointerIcon;

import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.LinkedHashMap;
import java.util.Map;

public class BrandProbe {
    static final Map<String, Integer> TYPES = new LinkedHashMap<>();
    static {
        TYPES.put("arrow", PointerIcon.TYPE_ARROW);
        TYPES.put("context_menu", PointerIcon.TYPE_CONTEXT_MENU);
        TYPES.put("hand", PointerIcon.TYPE_HAND);
        TYPES.put("help", PointerIcon.TYPE_HELP);
        TYPES.put("wait", PointerIcon.TYPE_WAIT);
        TYPES.put("cell", PointerIcon.TYPE_CELL);
        TYPES.put("crosshair", PointerIcon.TYPE_CROSSHAIR);
        TYPES.put("text", PointerIcon.TYPE_TEXT);
        TYPES.put("vertical_text", PointerIcon.TYPE_VERTICAL_TEXT);
        TYPES.put("alias", PointerIcon.TYPE_ALIAS);
        TYPES.put("copy", PointerIcon.TYPE_COPY);
        TYPES.put("nodrop", PointerIcon.TYPE_NO_DROP);
        TYPES.put("all_scroll", PointerIcon.TYPE_ALL_SCROLL);
        TYPES.put("horizontal_double_arrow", PointerIcon.TYPE_HORIZONTAL_DOUBLE_ARROW);
        TYPES.put("vertical_double_arrow", PointerIcon.TYPE_VERTICAL_DOUBLE_ARROW);
        TYPES.put("top_right_diagonal_double_arrow", PointerIcon.TYPE_TOP_RIGHT_DIAGONAL_DOUBLE_ARROW);
        TYPES.put("top_left_diagonal_double_arrow", PointerIcon.TYPE_TOP_LEFT_DIAGONAL_DOUBLE_ARROW);
        TYPES.put("zoom_in", PointerIcon.TYPE_ZOOM_IN);
        TYPES.put("zoom_out", PointerIcon.TYPE_ZOOM_OUT);
        TYPES.put("grab", PointerIcon.TYPE_GRAB);
        TYPES.put("grabbing", PointerIcon.TYPE_GRABBING);
    }
    static final String[] FILLS = {"black", "green", "red", "pink", "blue", "purple"};
    static final String[] STROKES = {"white", "black", "none"};

    public static void main(String[] args) throws Exception {
        Looper.prepareMainLooper();
        Context ctx = systemContext();
        switch (args.length > 0 ? args[0] : "") {
            case "pointers":
                pointers(ctx, args[1], args.length > 2 ? Float.parseFloat(args[2]) : 1f);
                break;
            case "palette":
                palette(ctx);
                break;
            case "resinfo":
                resinfo(ctx, args[1]);
                break;
            case "set-wallpaper":
                try (InputStream in = new FileInputStream(args[1])) {
                    int which = WallpaperManager.FLAG_SYSTEM | WallpaperManager.FLAG_LOCK;
                    int id = WallpaperManager.getInstance(ctx).setStream(in, null, true, which);
                    System.out.println("wallpaper set: " + args[1] + " id " + id);
                }
                break;
            default:
                System.err.println("usage: BrandProbe pointers OUTDIR [SCALE] | palette | set-wallpaper FILE");
                System.exit(2);
        }
        System.exit(0);
    }

    // The system context, as tools run through app_process get it: an ActivityThread that is not attached.
    static Context systemContext() throws Exception {
        Class<?> at = Class.forName("android.app.ActivityThread");
        Constructor<?> c = at.getDeclaredConstructor();
        c.setAccessible(true);
        Object thread = c.newInstance();
        Field cur = at.getDeclaredField("sCurrentActivityThread");
        cur.setAccessible(true);
        cur.set(null, thread);
        Method gsc = at.getDeclaredMethod("getSystemContext");
        return (Context) gsc.invoke(thread);
    }

    static void pointers(Context ctx, String out, float scale) throws Exception {
        Method load = PointerIcon.class.getDeclaredMethod("getLoadedSystemIcon", Context.class, int.class,
                boolean.class, float.class);
        Method fillRes = PointerIcon.class.getDeclaredMethod("vectorFillStyleToResource", int.class);
        Method strokeRes = PointerIcon.class.getDeclaredMethod("vectorStrokeStyleToResource", int.class);
        Method bitmap = PointerIcon.class.getDeclaredMethod("getBitmap");
        Field hx = PointerIcon.class.getDeclaredField("mHotSpotX");
        Field hy = PointerIcon.class.getDeclaredField("mHotSpotY");
        for (Method m : new Method[] {load, fillRes, strokeRes, bitmap}) m.setAccessible(true);
        hx.setAccessible(true);
        hy.setAccessible(true);
        System.out.println("type\tfill\tstroke\twidth\theight\thotspot_x\thotspot_y\topaque_px\tcentre_argb\tfile");
        for (Map.Entry<String, Integer> t : TYPES.entrySet()) {
            for (int f = 0; f < FILLS.length; f++) {
                for (int s = 0; s < STROKES.length; s++) {
                    // as PointerIconCache.getLoadedPointerIcon does
                    Resources.Theme theme = ctx.getResources().newTheme();
                    theme.setTo(ctx.getTheme());
                    theme.applyStyle((int) fillRes.invoke(null, f), true);
                    theme.applyStyle((int) strokeRes.invoke(null, s), true);
                    PointerIcon icon = (PointerIcon) load.invoke(null, new ContextThemeWrapper(ctx, theme),
                            t.getValue(), false, scale);
                    Bitmap b = (Bitmap) bitmap.invoke(icon);
                    String name = t.getKey() + "-" + FILLS[f] + "-" + STROKES[s] + ".png";
                    int opaque = 0;
                    for (int y = 0; y < b.getHeight(); y++) {
                        for (int x = 0; x < b.getWidth(); x++) {
                            if (Color.alpha(b.getPixel(x, y)) > 127) opaque++;
                        }
                    }
                    try (FileOutputStream o = new FileOutputStream(out + "/" + name)) {
                        b.compress(Bitmap.CompressFormat.PNG, 100, o);
                    }
                    System.out.printf("%s\t%s\t%s\t%d\t%d\t%.1f\t%.1f\t%d\t%08x\t%s%n", t.getKey(), FILLS[f],
                            STROKES[s], b.getWidth(), b.getHeight(), hx.getFloat(icon), hy.getFloat(icon), opaque,
                            b.getPixel(b.getWidth() / 2, b.getHeight() / 2), name);
                }
            }
        }
    }

    static void resinfo(Context ctx, String typeName) throws Exception {
        Resources r = ctx.getResources();
        String[] tn = typeName.split("/");
        int id = r.getIdentifier(tn[1], tn[0], "android");
        System.out.printf("%s id 0x%08x%n", typeName, id);
        if (tn[0].equals("bool")) {
            System.out.println("value " + r.getBoolean(id));
        } else if (tn[0].equals("string")) {
            System.out.println("value " + r.getString(id));
        } else if (tn[0].equals("drawable")) {
            android.content.res.XmlResourceParser x = r.getXml(id);
            int ev;
            while ((ev = x.next()) != org.xmlpull.v1.XmlPullParser.END_DOCUMENT) {
                if (ev == org.xmlpull.v1.XmlPullParser.START_TAG && x.getName().equals("path")) {
                    String d = x.getAttributeValue("http://schemas.android.com/apk/res/android", "pathData");
                    System.out.println("first pathData " + (d.length() > 60 ? d.substring(0, 60) + "..." : d));
                    break;
                }
            }
        }
    }

    static void palette(Context ctx) throws Exception {
        for (Field f : android.R.color.class.getFields()) {
            if (!f.getName().startsWith("system_")) continue;
            int id = f.getInt(null);
            System.out.printf("%s\t#%06X%n", f.getName(), ctx.getResources().getColor(id, null) & 0xFFFFFF);
        }
    }
}
