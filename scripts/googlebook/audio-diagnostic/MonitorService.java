// SPDX-License-Identifier: Apache-2.0
package org.openbook.diagnostics.audio;

import android.Manifest;
import android.app.*;
import android.app.usage.StorageStatsManager;
import android.bluetooth.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.*;
import android.os.*;
import android.os.storage.StorageManager;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Passive only: no AudioRecord/AudioTrack, audio focus, mode or routing writes. */
public final class MonitorService extends Service {
    public static volatile boolean running;
    public static volatile String lastStatus = "Ready";
    private final Handler h = new Handler(Looper.getMainLooper());
    private AudioManager audio;
    private BluetoothAdapter bt;
    private final Map<Integer, BluetoothProfile> profiles = new HashMap<>();
    private OutputStream writer;
    private long started, bytes;
    private boolean registered, callbacks;
    private final AudioDeviceCallback devices = new AudioDeviceCallback() {
        @Override public void onAudioDevicesAdded(AudioDeviceInfo[] d) { snapshot("devices_added"); }
        @Override public void onAudioDevicesRemoved(AudioDeviceInfo[] d) { snapshot("devices_removed"); }
    };
    private final AudioManager.OnCommunicationDeviceChangedListener communication = d -> snapshot("communication_changed");
    private final AudioManager.OnModeChangedListener mode = m -> snapshot("mode_changed");
    private final BluetoothProfile.ServiceListener profileListener = new BluetoothProfile.ServiceListener() {
        public void onServiceConnected(int id, BluetoothProfile p) {
            if (!running) { if (bt != null) bt.closeProfileProxy(id, p); return; }
            profiles.put(id, p); snapshot("profile_available");
        }
        public void onServiceDisconnected(int id) { profiles.remove(id); snapshot("profile_unavailable"); }
    };
    private final BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            // Never serialize the Intent or its BluetoothDevice extra (contains identifiers).
            JSONObject row = object("event", "bluetooth_event", "action", i.getAction(),
                "state", i.getIntExtra(BluetoothProfile.EXTRA_STATE, -1),
                "adapter_state", i.getIntExtra(BluetoothAdapter.EXTRA_STATE, -1),
                "sco_state", i.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, -1));
            record(row); snapshot("bluetooth_event_snapshot");
        }
    };
    private final Runnable tick = new Runnable() {
        public void run() {
            if (!running) return;
            if (SystemClock.elapsedRealtime() - started >= 30 * 60 * 1000L || bytes > 3 * 1024 * 1024) {
                lastStatus = "Capture limit reached"; stopSelf(); return;
            }
            snapshot("sample"); h.postDelayed(this, 5000);
        }
    };
    static JSONObject object(Object... pairs) {
        JSONObject o = new JSONObject();
        try { for (int i = 0; i < pairs.length; i += 2) o.put((String)pairs[i], pairs[i+1]); }
        catch (JSONException e) { throw new IllegalStateException(e); }
        return o;
    }
    private static JSONArray numbers(int[] a) { JSONArray j = new JSONArray(); for (int n : a) j.put(n); return j; }
    private static String type(int t) {
        switch (t) {
            case AudioDeviceInfo.TYPE_BUILTIN_MIC: return "built_in_mic";
            case AudioDeviceInfo.TYPE_BUILTIN_SPEAKER: return "speaker";
            case AudioDeviceInfo.TYPE_BLUETOOTH_A2DP: return "bluetooth_a2dp";
            case AudioDeviceInfo.TYPE_BLUETOOTH_SCO: return "bluetooth_sco";
            case AudioDeviceInfo.TYPE_BLE_HEADSET: return "ble_headset";
            case AudioDeviceInfo.TYPE_WIRED_HEADSET: return "wired_headset";
            default: return "type_" + t;
        }
    }
    private static Object device(AudioDeviceInfo d) {
        return d == null ? JSONObject.NULL : object("id", d.getId(), "type", type(d.getType()),
            "source", d.isSource(), "sink", d.isSink(), "sample_rates", numbers(d.getSampleRates()),
            "channel_counts", numbers(d.getChannelCounts()));
    }
    private static JSONObject fs(File f) {
        StatFs s = new StatFs(f.getPath());
        return object("total_bytes", s.getTotalBytes(), "available_bytes", s.getAvailableBytes(),
            "free_bytes", s.getFreeBytes(), "block_size", s.getBlockSizeLong());
    }
    private void record(JSONObject o) {
        if (writer == null) return;
        try {
            o.put("utc_ms", System.currentTimeMillis()); o.put("elapsed_ms", SystemClock.elapsedRealtime() - started);
            byte[] b = (o.toString() + "\n").getBytes(StandardCharsets.UTF_8);
            writer.write(b); writer.flush(); bytes += b.length;
        } catch (IOException | JSONException e) { lastStatus = "Report write failed"; stopSelf(); }
    }
    private void snapshot(String event) {
        if (!running || audio == null) return;
        JSONObject row = object("event", event);
        try {
            JSONArray all = new JSONArray(), available = new JSONArray(), recording = new JSONArray(), ps = new JSONArray();
            for (AudioDeviceInfo d : audio.getDevices(AudioManager.GET_DEVICES_ALL)) all.put(device(d));
            for (AudioDeviceInfo d : audio.getAvailableCommunicationDevices()) available.put(device(d));
            for (AudioRecordingConfiguration c : audio.getActiveRecordingConfigurations()) {
                recording.put(object("device", device(c.getAudioDevice()), "silenced", c.isClientSilenced(),
                    "source", c.getClientAudioSource(), "sample_rate", c.getClientFormat().getSampleRate(),
                    "channel_count", c.getClientFormat().getChannelCount()));
            }
            boolean permitted = checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
            if (permitted && bt != null) {
                for (int id : new int[]{BluetoothProfile.HEADSET, BluetoothProfile.A2DP, BluetoothProfile.LE_AUDIO}) {
                    BluetoothProfile p = profiles.get(id);
                    JSONObject profile = object("profile", id == BluetoothProfile.HEADSET ? "HFP" :
                        id == BluetoothProfile.A2DP ? "A2DP" : "LE_AUDIO", "connection_state", bt.getProfileConnectionState(id),
                        "proxy_available", p != null);
                    if (p != null) {
                        List<BluetoothDevice> connected = p.getConnectedDevices();
                        profile.put("connected_count", connected.size());
                        if (p instanceof BluetoothHeadset) {
                            int active = 0;
                            for (BluetoothDevice d : connected) if (((BluetoothHeadset)p).isAudioConnected(d)) active++;
                            profile.put("audio_connected_count", active);
                        }
                    }
                    ps.put(profile);
                }
                row.put("bluetooth_enabled", bt.isEnabled());
            }
            row.put("bluetooth_permission", permitted);
            row.put("mode", audio.getMode()); row.put("microphone_muted", audio.isMicrophoneMute());
            row.put("music_active", audio.isMusicActive()); row.put("devices", all);
            row.put("communication_device", device(audio.getCommunicationDevice()));
            row.put("available_communication_devices", available);
            row.put("recording_metadata_visible_to_app", recording);
            row.put("profiles", ps);
        } catch (RuntimeException | JSONException e) { try { row.put("access_error", e.getClass().getSimpleName()); } catch (JSONException ignored) {} }
        record(row);
    }
    @Override public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("capture", "Audio diagnostics", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, MonitorService.class).setAction("stop"),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(this, "capture").setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setContentTitle("OpenBook audio diagnostic running").setContentText("Route metadata only · 30 minute limit")
            .setContentIntent(open).setOngoing(true).addAction(new Notification.Action.Builder(null, "Stop", stop).build()).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(1, notification);
        started = SystemClock.elapsedRealtime();
        try { writer = new FileOutputStream(new File(getFilesDir(), "audio-report.jsonl")); }
        catch (IOException e) { lastStatus = "Cannot create report"; stopSelf(); return; }
        running = true; lastStatus = "Capturing";
        record(object("event", "start", "schema", "openbook-audio-diagnostic/1",
            "app_version", 1, "sdk", Build.VERSION.SDK_INT, "build", Build.DISPLAY,
            "scope", "Public route/profile metadata; no call content; other-app visibility may be limited"));
        try {
            record(object("event", "storage", "data_filesystem", fs(Environment.getDataDirectory()),
                "root_filesystem", fs(Environment.getRootDirectory()),
                "app_filesystem", fs(getFilesDir()),
                "android_storage_total_bytes", getSystemService(StorageStatsManager.class).getTotalBytes(StorageManager.UUID_DEFAULT)));
        } catch (Exception e) { record(object("event", "storage_error", "error", e.getClass().getSimpleName())); }
        audio = getSystemService(AudioManager.class);
        audio.registerAudioDeviceCallback(devices, h);
        audio.addOnCommunicationDeviceChangedListener(getMainExecutor(), communication);
        audio.addOnModeChangedListener(getMainExecutor(), mode);
        callbacks = true;
        IntentFilter filter = new IntentFilter();
        for (String action : new String[]{BluetoothAdapter.ACTION_STATE_CHANGED,
            BluetoothHeadset.ACTION_CONNECTION_STATE_CHANGED, BluetoothHeadset.ACTION_AUDIO_STATE_CHANGED,
            BluetoothA2dp.ACTION_CONNECTION_STATE_CHANGED, BluetoothA2dp.ACTION_PLAYING_STATE_CHANGED,
            AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED}) filter.addAction(action);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
        else registerReceiver(receiver, filter);
        registered = true;
        bt = getSystemService(BluetoothManager.class).getAdapter();
        if (bt != null && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED) {
            for (int id : new int[]{BluetoothProfile.HEADSET, BluetoothProfile.A2DP, BluetoothProfile.LE_AUDIO})
                try { bt.getProfileProxy(this, profileListener, id); }
                catch (RuntimeException e) { record(object("event", "profile_error", "profile", id, "error", e.getClass().getSimpleName())); }
        }
        h.post(tick);
    }
    @Override public int onStartCommand(Intent i, int flags, int id) {
        if (i != null && "stop".equals(i.getAction())) stopSelf();
        else if (i != null && "mark".equals(i.getAction())) snapshot("user_marked_problem");
        return START_NOT_STICKY;
    }
    @Override public void onDestroy() {
        h.removeCallbacks(tick);
        snapshot("stop"); running = false;
        if ("Capturing".equals(lastStatus)) lastStatus = "Report ready";
        if (callbacks) {
            audio.unregisterAudioDeviceCallback(devices);
            audio.removeOnCommunicationDeviceChangedListener(communication);
            audio.removeOnModeChangedListener(mode);
        }
        if (registered) unregisterReceiver(receiver);
        if (bt != null) for (Map.Entry<Integer, BluetoothProfile> p : profiles.entrySet()) bt.closeProfileProxy(p.getKey(), p.getValue());
        profiles.clear();
        try { if (writer != null) writer.close(); } catch (IOException ignored) {}
        writer = null; stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
    @Override public IBinder onBind(Intent i) { return null; }
}
