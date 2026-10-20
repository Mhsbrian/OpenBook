// SPDX-License-Identifier: Apache-2.0
package org.openbook.test.camera;

import android.app.Activity;
import android.graphics.ImageFormat;
import android.hardware.Camera;
import android.hardware.camera2.*;
import android.media.Image;
import android.media.ImageReader;
import android.os.*;
import android.util.Log;
import android.util.Size;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import java.nio.ByteBuffer;
import java.util.Collections;

/**
 * Bounded, foreground-only diagnostic using normal application camera access.
 * No network/storage permission, saved images, audio, or privacy override.
 * Logs only frame counts, dimensions and aggregate luma range; never pixels.
 */
@SuppressWarnings("deprecation")
public final class CameraProbeActivity extends Activity implements SurfaceHolder.Callback {
    private static final String TAG = "OpenBookCameraProbe";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Camera legacy;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private ImageReader reader;
    private int frames, min = 255, max;
    private long first, last;
    private boolean started, closed;
    private String api;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        api = getIntent().getStringExtra("api");
        if (!"1".equals(api) && !"2".equals(api)) {
            Log.e(TAG, "Specify --es api 1 or --es api 2");
            finish();
            return;
        }
        Log.i(TAG, "START api=" + api + " uid=" + android.os.Process.myUid() + " duration_ms=20000");
        SurfaceView view = new SurfaceView(this);
        setContentView(view);
        view.getHolder().addCallback(this);
        handler.postDelayed(() -> { close(); finish(); }, 20000);
    }

    @Override public void surfaceCreated(SurfaceHolder holder) {
        if (started || closed) return;
        started = true;
        try {
            if ("1".equals(api)) {
                legacy = Camera.open(0);
                Camera.Parameters p = legacy.getParameters();
                Camera.Size chosen = p.getSupportedPreviewSizes().get(0);
                for (Camera.Size size : p.getSupportedPreviewSizes())
                    if (size.width == 640 && size.height == 480) chosen = size;
                p.setPreviewSize(chosen.width, chosen.height);
                p.setPreviewFormat(ImageFormat.NV21);
                legacy.setParameters(p);
                Log.i(TAG, "CONFIG api=1 width=" + chosen.width + " height=" + chosen.height);
                final int lumaSize = chosen.width * chosen.height;
                legacy.setPreviewDisplay(holder);
                legacy.setErrorCallback((error, ignored) -> Log.e(TAG, "LEGACY_ERROR " + error));
                legacy.setPreviewCallback((data, ignored) -> {
                    if (data == null || closed) return;
                    for (int i = 0; i < Math.min(lumaSize, data.length); i += 257)
                        sample(data[i] & 255);
                    frame();
                });
                legacy.startPreview();
            } else {
                CameraManager manager = getSystemService(CameraManager.class);
                String[] ids = manager.getCameraIdList();
                if (ids.length == 0) throw new IllegalStateException("No camera IDs");
                String id = ids[0];
                Size[] sizes = manager.getCameraCharacteristics(id).get(
                    CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                    .getOutputSizes(ImageFormat.YUV_420_888);
                Size chosen = sizes[0];
                for (Size size : sizes)
                    if (size.getWidth() == 640 && size.getHeight() == 480) chosen = size;
                Log.i(TAG, "CONFIG api=2 id=" + id + " width=" + chosen.getWidth()
                    + " height=" + chosen.getHeight());
                reader = ImageReader.newInstance(chosen.getWidth(), chosen.getHeight(),
                    ImageFormat.YUV_420_888, 3);
                reader.setOnImageAvailableListener(source -> {
                    if (closed) return;
                    try (Image image = source.acquireLatestImage()) {
                        if (image == null) return;
                        Image.Plane y = image.getPlanes()[0];
                        ByteBuffer bytes = y.getBuffer();
                        // Honor row/pixel strides: padding is not image evidence.
                        for (int row = 0; row < image.getHeight(); row += 17)
                            for (int col = 0; col < image.getWidth(); col += 17)
                                sample(bytes.get(row * y.getRowStride()
                                    + col * y.getPixelStride()) & 255);
                        frame();
                    }
                }, handler);
                manager.openCamera(id, new CameraDevice.StateCallback() {
                    @Override public void onOpened(CameraDevice device) {
                        if (closed) { device.close(); return; }
                        camera = device;
                        try {
                            device.createCaptureSession(Collections.singletonList(reader.getSurface()),
                                new CameraCaptureSession.StateCallback() {
                                    @Override public void onConfigured(CameraCaptureSession configured) {
                                        if (closed) { configured.close(); return; }
                                        session = configured;
                                        try {
                                            CaptureRequest.Builder request = device.createCaptureRequest(
                                                CameraDevice.TEMPLATE_PREVIEW);
                                            request.addTarget(reader.getSurface());
                                            configured.setRepeatingRequest(request.build(), null, handler);
                                        } catch (Exception error) { failure(error); }
                                    }
                                    @Override public void onConfigureFailed(CameraCaptureSession failed) {
                                        failed.close();
                                        Log.e(TAG, "CONFIGURE_FAILED");
                                    }
                                }, handler);
                        } catch (Exception error) { failure(error); }
                    }
                    @Override public void onDisconnected(CameraDevice device) {
                        Log.e(TAG, "DISCONNECTED"); device.close();
                    }
                    @Override public void onError(CameraDevice device, int error) {
                        Log.e(TAG, "CAMERA2_ERROR " + error); device.close();
                    }
                }, handler);
            }
        } catch (Exception error) { failure(error); }
    }

    private void sample(int value) { min = Math.min(min, value); max = Math.max(max, value); }
    private void frame() {
        last = SystemClock.elapsedRealtime();
        if (++frames == 1) { first = last; Log.i(TAG, "FIRST_FRAME api=" + api); }
    }
    private void failure(Exception error) { Log.e(TAG, "FAILED api=" + api, error); }
    private void close() {
        if (closed) return;
        closed = true;
        handler.removeCallbacksAndMessages(null);
        if (legacy != null) {
            legacy.setPreviewCallback(null); legacy.release(); legacy = null;
        }
        if (session != null) session.close();
        if (camera != null) camera.close();
        if (reader != null) {
            reader.setOnImageAvailableListener(null, null);
            reader.close();
        }
        Log.i(TAG, "RESULT api=" + api + " frames=" + frames + " span_ms="
            + (frames > 1 ? last - first : 0) + " luma_min=" + (frames > 0 ? min : -1)
            + " luma_max=" + (frames > 0 ? max : -1));
    }
    @Override protected void onPause() { close(); super.onPause(); }
    @Override protected void onDestroy() { close(); super.onDestroy(); }
    @Override public void surfaceDestroyed(SurfaceHolder holder) { close(); }
    @Override public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {}
}
