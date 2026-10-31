// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

import android.content.pm.PackageInfo;
import android.content.pm.Signature;
import android.os.IBinder;

import java.lang.reflect.Method;
import java.security.MessageDigest;

/**
 * The certificates PackageManager reports for packages, as an app gets them, without an app or a screen (ANAL-210):
 * run as the shell user with app_process, it asks the "package" service for getPackageInfo(pkg, GET_SIGNATURES, user 0),
 * which goes through the same code path (ComputerEngine.generatePackageInfo) as an app's call, so the microG patch's
 * spoofing shows here too. Prints one line per package: name, SHA-1 and SHA-256 of each certificate, or "absent".
 *   adb push sigcheck.dex /data/local/tmp/ && adb shell app_process -cp /data/local/tmp/sigcheck.dex / SigCheck PKG...
 */
public class SigCheck {
    public static void main(String[] args) throws Exception {
        Method getService = Class.forName("android.os.ServiceManager").getMethod("getService", String.class);
        IBinder b = (IBinder) getService.invoke(null, "package");
        Object pm = Class.forName("android.content.pm.IPackageManager$Stub").getMethod("asInterface", IBinder.class)
                .invoke(null, b);
        Method getPackageInfo = pm.getClass().getMethod("getPackageInfo", String.class, long.class, int.class);
        for (String p : args) {
            PackageInfo pi = (PackageInfo) getPackageInfo.invoke(pm, p, 64L /* GET_SIGNATURES */, 0);
            StringBuilder sb = new StringBuilder(p);
            if (pi == null || pi.signatures == null) {
                sb.append(" absent");
            } else {
                for (Signature s : pi.signatures) {
                    sb.append(" sha1=").append(hex(MessageDigest.getInstance("SHA-1").digest(s.toByteArray())))
                      .append(" sha256=").append(hex(MessageDigest.getInstance("SHA-256").digest(s.toByteArray())));
                }
            }
            System.out.println(sb);
        }
    }

    private static String hex(byte[] d) {
        StringBuilder sb = new StringBuilder();
        for (byte x : d) sb.append(String.format("%02x", x));
        return sb.toString();
    }
}
