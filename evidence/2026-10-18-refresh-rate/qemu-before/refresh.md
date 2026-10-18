# Refresh rate in QEMU: anal212-before

| Check | Verdict | Facts |
|---|---|---|
| config | NO | {"fingerprint": "OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/eng.builde:userdebug/test-keys", "values": {"config_defaultRefreshRate": "60", "config_defaultPeakRefreshRate": "0"}, "overlays": ["[x] dev.anybook.overlay.desktop.framework", "[x] dev.anybook.overlay.pointer"], "dmd": ["mDefaultRefreshRate: 60.0", "mDefaultPeakRefreshRate: 0.0", "PRIORITY_DEFAULT_REFRESH_RATE -> RenderVot |
| policy | NO | {"resolution": "1920x1200", "active_hz": 75.0, "fastest_mode_hz": 75.0, "primary_render_max_hz": 60.0, "primary_physical_max_hz": "none", "render_hz_now": 37.5, "seconds_by_render_hz": {"75.00": 25.1, "37.50": 66.2}} |
| scroll | NO | {"samples_hz": [37.5, 37.5, 37.5, 37.5, 37.5, 37.5, 37.5, 37.5, 37.5, 37.5, 37.5, 37.5], "most_common_hz": 37.5, "seconds_by_render_hz_during": {"37.50": 22.2}} |
