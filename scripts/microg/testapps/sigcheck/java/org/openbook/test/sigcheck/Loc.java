// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
package org.openbook.test.sigcheck;

import android.app.Activity;
import android.location.Location;
import android.location.LocationManager;
import android.location.LocationRequest;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import org.json.JSONObject;

/**
 * One current location from each of the network, fused and gps providers (ANAL-210), as an app asks for it
 * (LocationManager.getCurrentLocation), with a timeout of "timeout_s" seconds (default 30) each, in parallel. One JSON
 * line goes to logcat (tag OpenBookLocCheck): per provider its package, whether it is enabled, and the fix or null.
 * Needs ACCESS_FINE_LOCATION (pm grant) and location on.
 *   am start -W -n org.openbook.test.sigcheck/.Loc [--ei timeout_s 30] [--ei quality 100|102]
 */
public class Loc extends Activity {
    private final JSONObject out = new JSONObject();
    private int pending;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        int timeout = getIntent().getIntExtra("timeout_s", 30);
        int quality = getIntent().getIntExtra("quality", 0);  // 100 high accuracy, 102 balanced; 0: the API's default
        LocationManager lm = getSystemService(LocationManager.class);
        Handler h = new Handler(Looper.getMainLooper());
        String[] providers = {LocationManager.NETWORK_PROVIDER, LocationManager.FUSED_PROVIDER, LocationManager.GPS_PROVIDER};
        pending = providers.length;
        for (String p : providers) {
            JSONObject o = new JSONObject();
            try {
                out.put(p, o);
                o.put("exists", lm.getAllProviders().contains(p));
                o.put("enabled", lm.isProviderEnabled(p));
                if (!lm.getAllProviders().contains(p)) {
                    done();
                    continue;
                }
                CancellationSignal cancel = new CancellationSignal();
                long t0 = System.currentTimeMillis();
                boolean[] answered = {false};  // a cancelled request gets no callback: the timeout answers instead
                java.util.function.Consumer<Location> got = loc -> {
                    if (answered[0]) return;
                    answered[0] = true;
                    try {
                        o.put("ms", System.currentTimeMillis() - t0);
                        o.put("fix", loc == null ? JSONObject.NULL : fix(loc));
                    } catch (Exception e) {
                        Log.e("OpenBookLocCheck", "json", e);
                    }
                    done();
                };
                if (quality == 0) {
                    lm.getCurrentLocation(p, cancel, getMainExecutor(), got);
                } else {
                    lm.getCurrentLocation(p, new LocationRequest.Builder(0).setQuality(quality)
                            .setDurationMillis(timeout * 1000L).build(), cancel, getMainExecutor(), got);
                }
                h.postDelayed(() -> {
                    if (answered[0]) return;
                    answered[0] = true;
                    cancel.cancel();
                    try {
                        o.put("fix", "timeout after " + timeout + " s");
                    } catch (Exception ignored) {
                    }
                    done();
                }, timeout * 1000L);
            } catch (Exception e) {
                try {
                    o.put("error", e.toString());
                } catch (Exception ignored) {
                }
                done();
            }
        }
    }

    private static JSONObject fix(Location l) throws Exception {
        JSONObject f = new JSONObject();
        f.put("provider", l.getProvider());
        f.put("lat", Math.round(l.getLatitude() * 100) / 100.0);   // two decimals: about a kilometre, enough here
        f.put("lon", Math.round(l.getLongitude() * 100) / 100.0);
        f.put("accuracy_m", l.hasAccuracy() ? Math.round(l.getAccuracy()) : -1);
        return f;
    }

    private void done() {
        if (--pending > 0) return;
        Log.i("OpenBookLocCheck", out.toString());
        finish();
    }
}
