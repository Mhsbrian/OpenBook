// SPDX-License-Identifier: Apache-2.0
package android.os;

/**
 * Compile-time stand-in for the framework's {@code android.os.UpdateEngine} (@SystemApi): only the
 * members OpenBook Update calls, with the framework's signatures. Never packaged (compileOnly).
 */
public class UpdateEngine {
    /** Status values reported to {@link UpdateEngineCallback#onStatusUpdate}. */
    public static final class UpdateStatusConstants {
        public static final int IDLE = 0;
        public static final int CHECKING_FOR_UPDATE = 1;
        public static final int UPDATE_AVAILABLE = 2;
        public static final int DOWNLOADING = 3;
        public static final int VERIFYING = 4;
        public static final int FINALIZING = 5;
        public static final int UPDATED_NEED_REBOOT = 6;
        public static final int REPORTING_ERROR_EVENT = 7;
        public static final int ATTEMPTING_ROLLBACK = 8;
        public static final int DISABLED = 9;
    }

    public UpdateEngine() {
        throw new RuntimeException("Stub!");
    }

    public boolean bind(UpdateEngineCallback callback, Handler handler) {
        throw new RuntimeException("Stub!");
    }

    public boolean unbind() {
        throw new RuntimeException("Stub!");
    }

    /** Applies a payload from an http(s):// or file:// URL; headers are the payload's properties (KEY=VALUE). */
    public void applyPayload(String url, long offset, long size, String[] headerKeyValuePairs) {
        throw new RuntimeException("Stub!");
    }

    /** Stops an ongoing update (the slot being written is left incomplete and is not activated). */
    public void cancel() {
        throw new RuntimeException("Stub!");
    }

    /** Error codes reported to {@link UpdateEngineCallback#onPayloadApplicationComplete}. */
    public static final class ErrorCodeConstants {
        public static final int SUCCESS = 0;
        public static final int UPDATED_BUT_NOT_ACTIVE = 52;
    }
}
