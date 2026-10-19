// SPDX-License-Identifier: Apache-2.0
package dev.openbook.nativefallback;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.ServiceInfo;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Parcel;
import android.os.SystemClock;
import android.util.Log;
import android.widget.TextView;

/** Checks synchronous rejection and executes guest JNI in a managed isolated fallback. */
public final class ProbeActivity extends Activity {
    private static final String TAG = "NativeFallbackProbe";
    private boolean complete;
    private TextView result;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        result = new TextView(this);
        setContentView(result);
        Log.i(TAG, "intent=" + getIntent().toUri(Intent.URI_INTENT_SCHEME));
        String aliasControl = getIntent().getStringExtra("alias_control");
        boolean hostControl = "host".equals(aliasControl);
        Handler handler = new Handler(getMainLooper());
        handler.postDelayed(() -> {
            if (!complete) report("FAIL fallback timed out");
        }, 15000);
        boolean positiveAlias = "positive".equals(aliasControl);
        boolean negativeAlias = "permission".equals(aliasControl);
        String className = positiveAlias
                ? "org.chromium.content.app.NativeOnlySandboxedProcessService1"
                : negativeAlias ? "org.chromium.content.app.NativeOnlySandboxedProcessService0"
                : getPackageName() + ".NativeOnly";
        try {
            int flags = getPackageManager().getServiceInfo(
                    new ComponentName(this, className), 0).flags;
            Log.i(TAG, "declared_service_flags=0x" + Integer.toHexString(flags));
            if ((flags & ServiceInfo.FLAG_NATIVE_SERVICE) == 0) {
                report("FAIL fixture missing nativeService flag; check framework resource IDs");
                return;
            }
        } catch (Exception e) {
            report("FAIL fixture lookup: " + e);
            return;
        }
        long start = SystemClock.elapsedRealtime();
        ServiceConnection unused = new ServiceConnection() {
            public void onServiceConnected(ComponentName name, IBinder service) {}
            public void onServiceDisconnected(ComponentName name) {}
        };
        ServiceConnection initial = positiveAlias ? translatedConnection(className) : unused;
        Intent nativeIntent = new Intent().setClassName(this, className);
        boolean accepted = bindService(nativeIntent, initial, hostControl ? 0 : BIND_AUTO_CREATE);
        long millis = SystemClock.elapsedRealtime() - start;
        Log.i(TAG, "native_bind=" + accepted + " elapsed_ms=" + millis);
        if (hostControl) {
            if (accepted) unbindService(unused);
            report(accepted ? "PASS host native-only bind accepted" : "FAIL host native bind rejected");
            return;
        }
        if (positiveAlias) {
            if (!accepted) report("FAIL compatible alias rejected");
            return;
        }
        if (negativeAlias && !accepted) {
            report("PASS permission mismatch rejected");
            return;
        }
        if (accepted) {
            unbindService(unused);
            report("FAIL guest native-only bind accepted");
            return;
        }
        if (millis >= 1000) {
            report("FAIL guest native-only rejection exceeded 1000 ms");
            return;
        }
        boolean fallback = bindService(new Intent(this, ManagedService.class),
                translatedConnection(null), BIND_AUTO_CREATE);
        if (!fallback) report("FAIL managed fallback bind rejected");
    }

    private ServiceConnection translatedConnection(String expectedClass) {
        return new ServiceConnection() {
            public void onServiceConnected(ComponentName name, IBinder service) {
                Parcel data = Parcel.obtain(), reply = Parcel.obtain();
                try {
                    if (expectedClass != null && !expectedClass.equals(name.getClassName())) {
                        throw new IllegalStateException("callback did not preserve original component: " + name);
                    }
                    if (!service.transact(IBinder.FIRST_CALL_TRANSACTION, data, reply, 0)) {
                        throw new IllegalStateException("transaction rejected");
                    }
                    reply.readException();
                    int answer = reply.readInt();
                    report(answer == 42 ? (expectedClass == null
                            ? "PASS translated isolated JNI returned 42"
                            : "PASS compatible alias translated JNI returned 42")
                            : "FAIL JNI answer=" + answer);
                } catch (Exception e) {
                    report("FAIL " + e);
                } finally {
                    data.recycle(); reply.recycle(); unbindService(this);
                }
            }
            public void onServiceDisconnected(ComponentName name) {}
        };
    }

    private void report(String message) {
        complete = true;
        result.setText(message);
        Log.i(TAG, message);
    }
}
