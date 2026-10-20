// SPDX-License-Identifier: Apache-2.0
package org.openbook.diagnostics.audio;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.*;
import android.provider.Settings;
import android.widget.*;
import java.io.*;

public final class MainActivity extends Activity {
    private TextView status;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        public void run() {
            status.setText(MonitorService.running ? "Recording route metadata · stop after reproducing the issue"
                : "Stopped · " + MonitorService.lastStatus);
            ui.postDelayed(this, 1000);
        }
    };
    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL); body.setPadding(24, 24, 24, 24);
        ScrollView scroll = new ScrollView(this); scroll.addView(body); setContentView(scroll);
        TextView title = new TextView(this); title.setText("OpenBook Audio Check"); title.setTextSize(26); body.addView(title);
        TextView help = new TextView(this);
        help.setText("Start before connecting your earbuds, then use Teams normally. Return and mark a problem "
            + "when convenient, stop, and save the report to attach to the issue.\n\n"
            + "Records audio devices, communication routes, Bluetooth profile states and storage capacity. "
            + "No call audio, microphone access, Bluetooth names/addresses, network upload or routing changes. "
            + "Android may hide another app's recording route; this report is not a full system log.\n\n"
            + "Runs for up to 30 minutes or 3 MiB. Starting again replaces the previous report; save it first.");
        help.setTextSize(16); body.addView(help);
        status = new TextView(this); status.setPadding(0, 20, 0, 20); body.addView(status);
        button(body, "Start diagnostic", () -> {
            if (MonitorService.running) return;
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(Build.VERSION.SDK_INT >= 33
                    ? new String[]{Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.POST_NOTIFICATIONS}
                    : new String[]{Manifest.permission.BLUETOOTH_CONNECT}, 1);
            } else startCapture();
        });
        button(body, "Mark an audio problem", () -> {
            if (MonitorService.running) startService(new Intent(this, MonitorService.class).setAction("mark"));
            else toast("Start the diagnostic first.");
        });
        button(body, "Stop diagnostic", () -> stopService(new Intent(this, MonitorService.class)));
        button(body, "Save report", () -> {
            if (MonitorService.running) { toast("Stop the diagnostic before saving."); return; }
            if (!new File(getFilesDir(), "audio-report.jsonl").isFile()) { toast("No report yet."); return; }
            Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/x-ndjson")
                .addCategory(Intent.CATEGORY_OPENABLE)
                .putExtra(Intent.EXTRA_TITLE, "OpenBook-audio-" + System.currentTimeMillis() + ".jsonl");
            startActivityForResult(i, 2);
        });
        button(body, "Open Bluetooth settings", () -> startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
        TextView extra = new TextView(this);
        extra.setText("\nFor deeper system logs: Developer options → Take bug report after reproducing. "
            + "Bug reports may include personal information. Review before sharing. "
            + "Use a test call for any optional Bluetooth HCI capture, and turn it off afterward.");
        body.addView(extra);
    }
    private void button(LinearLayout body, String text, Runnable action) {
        Button b = new Button(this); b.setText(text); b.setOnClickListener(v -> action.run()); body.addView(b);
    }
    private void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }
    private void startCapture() { startForegroundService(new Intent(this, MonitorService.class)); }
    @Override public void onRequestPermissionsResult(int n, String[] p, int[] r) {
        super.onRequestPermissionsResult(n, p, r);
        if (n == 1) startCapture(); // Denial is recorded; audio/storage observation still works.
    }
    @Override protected void onResume() { super.onResume(); ui.post(refresh); }
    @Override protected void onPause() { ui.removeCallbacks(refresh); super.onPause(); }
    @Override protected void onActivityResult(int n, int result, Intent data) {
        super.onActivityResult(n, result, data);
        if (n != 2 || result != RESULT_OK || data == null || data.getData() == null) return;
        try (InputStream in = new FileInputStream(new File(getFilesDir(), "audio-report.jsonl"));
             OutputStream out = getContentResolver().openOutputStream(data.getData(), "wt")) {
            if (out == null) throw new IOException("No destination");
            byte[] buffer = new byte[16384]; int count;
            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            toast("Report saved. Attach it to the issue.");
        } catch (IOException e) { toast("Could not save report: " + e.getClass().getSimpleName()); }
    }
}
