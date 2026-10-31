// SPDX-License-Identifier: Apache-2.0
package dev.openbook.nativefallback;

import android.app.Service;
import android.content.Intent;
import android.os.Binder;
import android.os.IBinder;
import android.os.Parcel;

public class ManagedService extends Service {
    static { System.loadLibrary("fallbackprobe"); }
    private static native int answer();
    @Override public IBinder onBind(Intent intent) {
        return new Binder() {
            @Override protected boolean onTransact(int code, Parcel data, Parcel reply, int flags) {
                if (code != FIRST_CALL_TRANSACTION) return false;
                reply.writeNoException();
                reply.writeInt(answer());
                return true;
            }
        };
    }
}
