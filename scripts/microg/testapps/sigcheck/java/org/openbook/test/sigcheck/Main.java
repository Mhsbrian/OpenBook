// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
package org.openbook.test.sigcheck;

import android.app.Activity;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Bundle;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.FileOutputStream;
import java.security.MessageDigest;

/**
 * What an ordinary app sees of other packages' signatures (ANAL-210): for each package in the "pkgs" extra
 * (default microG's three), the SHA-1 and SHA-256 of every certificate PackageManager returns with GET_SIGNATURES
 * and with GET_SIGNING_CERTIFICATES. That is how microG's self-check and Google's client libraries look
 * (PackageUtils.firstSignatureDigest). One JSON line goes to logcat (tag OpenBookSigCheck) and to
 * files/sigcheck.json, then the activity finishes.
 *   am start -W -n org.openbook.test.sigcheck/.Main [--es pkgs a,b]
 */
public class Main extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        String pkgs = getIntent().getStringExtra("pkgs");
        if (pkgs == null) pkgs = "com.google.android.gms,com.android.vending,com.google.android.gsf";
        JSONObject out = new JSONObject();
        try {
            PackageManager pm = getPackageManager();
            for (String p : pkgs.split(",")) {
                JSONObject o = new JSONObject();
                try {
                    PackageInfo a = pm.getPackageInfo(p, PackageManager.GET_SIGNATURES);
                    PackageInfo c = pm.getPackageInfo(p, PackageManager.GET_SIGNING_CERTIFICATES);
                    o.put("installed", true);
                    o.put("version_code", a.getLongVersionCode());
                    o.put("system", (a.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0);
                    o.put("signatures", digests(a.signatures));
                    SigningInfo si = c.signingInfo;
                    o.put("signing_certificates", si == null ? null
                            : digests(si.hasMultipleSigners() ? si.getApkContentsSigners() : si.getSigningCertificateHistory()));
                } catch (PackageManager.NameNotFoundException e) {
                    o.put("installed", false);
                }
                out.put(p, o);
            }
            String s = out.toString();
            Log.i("OpenBookSigCheck", s);
            try (FileOutputStream f = new FileOutputStream(getFilesDir() + "/sigcheck.json")) {
                f.write(s.getBytes("UTF-8"));
            }
        } catch (Exception e) {
            Log.e("OpenBookSigCheck", "failed", e);
        }
        finish();
    }

    private static JSONArray digests(Signature[] sigs) throws Exception {
        JSONArray a = new JSONArray();
        if (sigs == null) return a;
        for (Signature s : sigs) {
            JSONObject d = new JSONObject();
            d.put("sha1", hex(MessageDigest.getInstance("SHA-1").digest(s.toByteArray())));
            d.put("sha256", hex(MessageDigest.getInstance("SHA-256").digest(s.toByteArray())));
            a.put(d);
        }
        return a;
    }

    private static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }
}
