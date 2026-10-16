// AnyBook ARM-compat probe (ANAL-180). One APK per ABI; the native library does the work.
// Results go to logcat (tag AnyBookProbe) as "PROBE_RESULT <test> PASS|FAIL|SKIP <detail>",
// to the screen, and to files/probe-results.txt.
package dev.anybook.probe;

import android.app.Activity;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class MainActivity extends Activity {
    static final String TAG = "AnyBookProbe";
    static final String[] JAVA_TESTS = {"java_jni_args", "java_jni_exception", "java_jni_register_natives", "java_jni_callbacks"};

    private TextView view;
    private final StringBuilder out = new StringBuilder();
    public int field = 7;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        view = new TextView(this);
        view.setTypeface(Typeface.MONOSPACE);
        view.setTextSize(11);
        ScrollView sv = new ScrollView(this);
        sv.addView(view);
        setContentView(sv);
        final String mode = getIntent().getStringExtra("mode");
        final String arg = getIntent().getStringExtra("arg");
        new Thread(() -> run(mode == null ? "tests" : mode, arg), "probe-main").start();
    }

    private void emit(String line) {
        Log.i(TAG, line);
        synchronized (out) {
            out.append(line).append('\n');
        }
        runOnUiThread(() -> {
            synchronized (out) {
                view.setText(out.toString());
            }
        });
    }

    private void run(String mode, String arg) {
        emit("PROBE_START pkg=" + getPackageName() + " mode=" + mode + " abis=" + String.join(",", Build.SUPPORTED_ABIS)
                + " os.arch=" + System.getProperty("os.arch") + " sdk=" + Build.VERSION.SDK_INT);
        try {
            System.loadLibrary("probe");
        } catch (Throwable t) {
            emit("PROBE_RESULT load FAIL " + t);
            emit("PROBE_DONE pass=0 fail=1 skip=0");
            save();
            return;
        }
        emit("PROBE_RESULT load PASS " + nativeInfo());
        if ("bench".equals(mode)) {
            bench(arg);
            return;
        }
        List<String> tests = new ArrayList<>(Arrays.asList(JAVA_TESTS));
        tests.addAll(Arrays.asList(listTests()));
        int pass = 1, fail = 0, skip = 0;
        for (String t : tests) {
            if (arg != null && !arg.equals(t)) continue;
            emit("PROBE_BEGIN " + t);
            long t0 = SystemClock.elapsedRealtime();
            String r;
            try {
                r = t.startsWith("java_") ? javaTest(t) : runTest(t, getApplicationInfo().nativeLibraryDir);
            } catch (Throwable e) {
                r = "FAIL java exception " + e;
            }
            emit("PROBE_RESULT " + t + " " + r + " ms=" + (SystemClock.elapsedRealtime() - t0));
            if (r.startsWith("PASS")) pass++;
            else if (r.startsWith("SKIP")) skip++;
            else fail++;
        }
        emit("PROBE_DONE pass=" + pass + " fail=" + fail + " skip=" + skip);
        save();
    }

    private void bench(String arg) {
        String args = arg == null ? "0x0 0x0 0x66 300000" : arg;
        try {
            System.loadLibrary("cmark");
        } catch (Throwable t) {
            emit("PROBE_BENCH_FAIL " + t);
            return;
        }
        long t0 = SystemClock.elapsedRealtimeNanos();
        String res = nativeBench(args);
        long t1 = SystemClock.elapsedRealtimeNanos();
        for (String l : res.split("\n")) emit("PROBE_BENCH " + l);
        emit("PROBE_BENCH_DONE wall_ms=" + (t1 - t0) / 1000000);
        save();
    }

    private void save() {
        try (FileWriter w = new FileWriter(new File(getFilesDir(), "probe-results.txt"))) {
            synchronized (out) {
                w.write(out.toString());
            }
        } catch (Exception e) {
            Log.w(TAG, "save failed", e);
        }
    }

    // ---- Java-side JNI tests ----
    private String javaTest(String t) {
        switch (t) {
            case "java_jni_args": {
                // 20 mixed arguments: more than the arm64 and x86_64 register sets, so some go on the stack.
                float nan = Float.intBitsToFloat(0x7fa00001);
                int[] arr = {1, 2, 3, 4, 5, -6};
                String want = fmtArgs(-1, 0x123456789abcL, 1.5f, -0.0, true, (byte) -5, 'é', (short) -300,
                        Integer.MAX_VALUE, Long.MIN_VALUE, nan, Double.MIN_VALUE, "süß", arr,
                        3.25f, 1e300, 42, -7L, Float.MIN_VALUE, Math.PI);
                String got = nativeArgs(-1, 0x123456789abcL, 1.5f, -0.0, true, (byte) -5, 'é', (short) -300,
                        Integer.MAX_VALUE, Long.MIN_VALUE, nan, Double.MIN_VALUE, "süß", arr,
                        3.25f, 1e300, 42, -7L, Float.MIN_VALUE, Math.PI);
                return want.equals(got) ? "PASS checks=1" : "FAIL want=[" + want + "] got=[" + got + "]";
            }
            case "java_jni_exception":
                try {
                    nativeThrow("boom");
                    return "FAIL no exception";
                } catch (IllegalStateException e) {
                    return "boom".equals(e.getMessage()) ? "PASS checks=1" : "FAIL msg=" + e.getMessage();
                }
            case "java_jni_register_natives":
                return registeredAdd(40, 2) == 42 ? "PASS checks=1" : "FAIL";
            case "java_jni_callbacks":
                return nativeCallbacks();
        }
        return "FAIL unknown";
    }

    static String hx(float v) {
        return String.format("%08x", Float.floatToRawIntBits(v));
    }

    static String hx(double v) {
        return String.format("%016x", Double.doubleToRawLongBits(v));
    }

    static String fmtArgs(int a, long b, float c, double d, boolean e, byte f, char g, short h, int i, long j,
                          float k, double l, String m, int[] n, float o, double p, int q, long r, float s, double t) {
        int sum = 0;
        for (int x : n) sum += x;
        return a + "|" + b + "|" + hx(c) + "|" + hx(d) + "|" + (e ? 1 : 0) + "|" + f + "|" + (int) g + "|" + h + "|" + i + "|" + j
                + "|" + hx(k) + "|" + hx(l) + "|" + m + "|" + sum + "|" + hx(o) + "|" + hx(p) + "|" + q + "|" + r + "|" + hx(s) + "|" + hx(t);
    }

    // Called from native code.
    public int callback(int x, String s) {
        return x * 2 + s.length();
    }

    public void throwingCallback() {
        throw new IllegalArgumentException("from java");
    }

    public static int staticCallback(int x) {
        return 2 * x + 1;
    }

    public static String fmtFloats(float a, double b, float c, double d, int e, float f, double g, float h, double i,
                                   float j, long k, float l, double m) {
        return hx(a) + "|" + hx(b) + "|" + hx(c) + "|" + hx(d) + "|" + e + "|" + hx(f) + "|" + hx(g) + "|" + hx(h) + "|" + hx(i)
                + "|" + hx(j) + "|" + k + "|" + hx(l) + "|" + hx(m);
    }

    static native String nativeInfo();
    static native String[] listTests();
    static native String runTest(String name, String libDir);
    static native String nativeArgs(int a, long b, float c, double d, boolean e, byte f, char g, short h, int i, long j,
                                    float k, double l, String m, int[] n, float o, double p, int q, long r, float s, double t);
    static native void nativeThrow(String msg);
    static native int registeredAdd(int a, int b);
    native String nativeCallbacks();
    static native String nativeBench(String args);
}
