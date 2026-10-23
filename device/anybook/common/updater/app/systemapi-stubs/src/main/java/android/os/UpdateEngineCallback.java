// SPDX-License-Identifier: Apache-2.0
package android.os;

/** Compile-time stand-in for the framework's {@code android.os.UpdateEngineCallback} (@SystemApi). */
public abstract class UpdateEngineCallback {
    public abstract void onStatusUpdate(int status, float percent);

    public abstract void onPayloadApplicationComplete(int errorCode);
}
