#!/usr/bin/env python3
"""The ANAL-204 triage decisions for the 218 Googlebook flags AOSP 17 declares, merged with flag-facts.py output into
device/anybook/common/desktop/release/googlebook-triage.tsv (docs/googlebook-flags.md).

  scripts/ui/flag-facts.py evidence/2026-10-17-gbos-ui/flags/googlebook-on-openbook-off.tsv ~/anybook/aosp/src > facts.tsv
  scripts/ui/flag-triage.py facts.tsv > device/anybook/common/desktop/release/googlebook-triage.tsv

Decisions (enable in a group, defer, skip, drop) and reasons are written here by hand. Rerun after an AOSP sync: the
asserts fail if a "no reader" flag gains a reader or an enabled flag loses all of them.
"""
import sys

NOOP = "no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing"
D = {}


def d(cat, dec, grp, reason, *flags):
    for f in flags:
        assert f not in D, f
        D[f] = (cat, dec, grp, reason)


W, S, L, SH = "com.android.window.flags.", "com.android.systemui.", "com.android.launcher3.", "com.android.wm.shell."

# ---- Group 1: window shadows and resizing
d("visual", "enable", "1", "box shadows on freeform windows (WM Shell window decoration)", W + "enable_freeform_box_shadows_v2")
d("visual", "enable", "1", "box shadows on picture-in-picture windows", SH + "enable_pip_box_shadows_v2")
d("bugfix", "enable", "1", "applies the colour transform to box shadows and borders in RenderEngine; pairs with the shadows",
  "com.android.graphics.surfaceflinger.flags.color_transform_box_shadows_and_border")
d("desktop", "enable", "1", "client-side fluid-resize pipeline (batched config changes, caption insets); Googlebook ships it",
  W + "improve_fluid_resizing_performance")
d("desktop", "enable", "1", "no visible effect in AOSP 17 (C): DragPositioningCallbackUtility reports the size-constraint "
  "violation, but ResizeTaskPositioner discards it and the cursor stays a resize arrow (type 1017 on both builds); "
  "harmless, kept for when the cursor code lands", W + "enable_no_resize_cursor")
d("bugfix", "enable", "1", "drag-move/resize ignores events from a second input device", W + "filter_events_from_irrelevant_devices_in_drag_move_resize")
d("visual", "skip", "-", NOOP, W + "perfect_edge")

# ---- Group 2: blur
d("visual", "enable", "2", "blur behind the power menu and volume dialog (needs config_enableBlurExpansion, default true)",
  S + "blur_on_more_surfaces")
d("visual", "enable", "2", "blur behind Launcher folders and long-press menus", L + "blur_on_more_surfaces")

# ---- Group 3: taskbar and desktop behaviour
d("desktop", "enable", "3", "peek at the home screen behind desktop windows (action corner, WM Shell)", W + "enable_home_screen_peeking")
d("desktop", "enable", "3", "new windows cascade in steps instead of all opening at one spot", W + "enable_stepped_cascading")
d("desktop", "enable", "3", "app header with window controls on fullscreen tasks in desktop mode", W + "enable_fullscreen_window_controls")
d("desktop", "enable", "3", "one maximize/layout menu instead of the windowing pill plus menu", W + "enable_consolidated_window_options")
d("desktop", "enable", "3", "taskbar shows recent apps instead of hotseat predictions", "com.android.systemui.shared.enable_recents_in_taskbar")
d("bugfix", "enable", "3", "minimizing the last window of a desk animates and stays in desktop mode", W + "desktop_minimize_last_task_bugfix")
d("bugfix", "drop", "-", "crashes SystemUI in AOSP 17 (C, ANAL-204 v2 build): restoring a minimized window from the taskbar "
  "calls DefaultWindowDecoration.updateDragResizeListenerIfNeeded with no decoration container surface "
  "(IllegalStateException on wmshell.main); the flag's code is incomplete in this snapshot",
  W + "enable_add_window_decoration_to_all_tasks")
d("bugfix", "enable", "3", "a taskbar click collapses an open notification shade", L + "enable_collapse_sysui_panels_on_taskbar_click")
d("desktop", "enable", "3", "copy/paste for files on the home screen (we ship show_files_on_home_screen)", L + "enable_home_screen_files_copy_paste")
d("desktop", "enable", "3", "rename files on the home screen", L + "enable_home_screen_files_renaming")
d("desktop", "enable", "3", "desktop layout for the share sheet (Chooser)", "com.android.intentresolver.desktop_ui")
d("desktop", "enable", "3", "Files: Peek preview of a file (desktop quick look); needs use_material3, which is on",
  "com.android.documentsui.flags.use_peek_preview_ro")
d("desktop", "enable", "3", "Files: opens documents with an approved handler app; needs use_material3",
  "com.android.documentsui.flags.use_approved_document_handler")
d("desktop", "enable", "3", "on the lock screen any key opens the bouncer (keyboard laptops)", S + "press_any_key_to_access_bouncer_2")
d("desktop", "drop", "-", "empties the notification shade in AOSP 17 (C, ANAL-204 v2 and v3 builds): OpenBook disables the lock "
  "screen by default (config_disableLockscreenByDefault), so SystemUI starts on the Gone scene, the keyguard blueprint's "
  "NotificationStackScrollLayoutSection never binds the stack, and its rows are never laid out; with a PIN set "
  "(initial scene Lockscreen) the same image shows them", S + "start_on_gone_scene_if_no_lockscreen")
d("desktop", "skip", "-", NOOP, L + "enable_taskbar_icon_desktop_clicks")
d("desktop", "skip", "-", NOOP, W + "enable_desktop_taskbar_in_fullscreen_mode")
d("bugfix", "skip", "-", NOOP, W + "appheader_launch_color_bugfix")
d("desktop", "skip", "-", NOOP, W + "enable_fullscreen_in_new_task_preference")
d("bugfix", "skip", "-", NOOP, W + "show_when_locked_desktop_bugfix")
d("desktop", "skip", "-", NOOP, L + "enable_taskbar_customization")
d("bugfix", "skip", "-", NOOP, SH + "consolidate_split_keyboard_shortcut_controllers")
d("desktop", "defer", "-", "only acts on config_desktopLaunchInFullscreenPackages, empty in AOSP (Googlebook lists 26 games); "
  "needs an owner-approved list", W + "launch_games_in_fullscreen_by_allowlist")
d("desktop", "defer", "-", "lid-close Quick Doze: no lid in Cuttlefish; take with the G14 power work (docs/power-input.md)",
  "com.android.server.deviceidle.quick_doze_on_lid_close")

# ---- Group 4: SystemUI, Launcher and Settings polish
d("bugfix", "enable", "4", "tooltips on Quick Settings tiles (mouse hover)", S + "enable_qs_tile_tooltips")
d("desktop", "enable", "4", "hovering a heads-up notification pauses its dismiss timer", S + "hun_timer_pause_on_hover")
d("visual", "enable", "4", "heads-up notifications open expanded", S + "default_hun_expansion")
d("bugfix", "enable", "4", "Compose long-press menu with expandable sections (Launcher and taskbar)", L + "expandable_long_press_menu")
d("visual", "enable", "4", "Launcher reveal animation when another process runs the transition", L + "fallback_reveal_animation")
d("desktop", "enable", "4", "right-click (context click) on a notification opens its settings", S + "inline_notification_settings_access")
d("visual", "enable", "4", "launch/return animations pick their target dynamically", S + "animation_library_dynamic_target_resolution")
d("visual", "enable", "4", "status bar system icons drawn in Compose (needs scene_container and new_status_bar_icons, both on)",
  S + "status_bar_system_status_icons_in_compose")
d("visual", "enable", "4", "refreshed Compose status icons; pairs with status_bar_system_status_icons_in_compose",
  S + "status_icons_in_compose_refresh")
d("visual", "enable", "4", "Internet tile uses the details view instead of the legacy dialog (we ship qs_tile_detailed_view)",
  S + "internet_dialog_delegate_legacy_deprecation")
d("visual", "enable", "4", "All Apps drawn on its own surface", L + "all_apps_surface")
d("visual", "enable", "4", "share sheet remembers the include-link checkbox", "com.android.intentresolver.include_link_sticky_checkbox")
d("visual", "enable", "4", "SystemUI-styled IME switcher menu (base of ime_switcher_menu_systemui_style_update_desktop, which we ship)",
  "android.view.inputmethod.ime_switcher_menu_systemui_style_update")
d("desktop", "enable", "4", "setting to show or hide the IME switcher button", "android.view.inputmethod.ime_switcher_button_in_navbar_setting")
d("visual", "enable", "4", "Clear/Confirm buttons on the Settings password confirmation screen",
  "com.android.settings.flags.show_footer_buttons_on_password_confirm")
d("bugfix", "enable", "4", "storage percentage formatting in Settings (RTL)", "com.android.settings.flags.storage_summary_percentage_alignment")
d("visual", "skip", "-", NOOP, S + "notification_animated_action_style_2026")
d("visual", "skip", "-", NOOP, L + "enable_compose_for_options_popup_menu_dialog")
d("visual", "skip", "-", NOOP, L + "enable_widgets_section_in_options_menu")
d("visual", "skip", "-", "no effect: config_isStatusBarConnectedDisplayChipEnabled is true by default",
  S + "status_bar_is_connected_display_chip_controlled_by_config")
d("visual", "skip", "-", "needs a notes-role app; OpenBook ships none", S + "enable_note_in_action_corner", S + "enable_note_qs_tile")
d("visual", "skip", "-", "needs config_notificationAlertsChannel, which we do not set", S + "notification_storage_alerts_channel")
d("visual", "defer", "-", "Wallpaper picker refactor; take with the wallpaper work (B4/B6)",
  "com.android.wallpaper.refactor_wallpaper_preview_screen_flag", "com.android.wallpaper.refactor_wallpaper_info_flag")
d("visual", "defer", "-", "only acts with config_optimizeDefaultWallpaper=true (Googlebook sets it); take with the wallpaper work (B4)",
  "android.app.optimize_default_wallpaper")

# ---- Group 5: remaining applicable bugfixes (UI, WM, graphics, media, a11y, framework)
G5 = [
    (W + "add_bg_color_for_transparent_bubbles", "bubbles get a background colour (no transparent layers)"),
    (W + "camera_compat_ignore_requested_orientation_allowed", "camera compat in freeform windows"),
    (W + "camera_compat_update_treatment_on_rotation", "camera compat treatment follows display rotation"),
    (W + "consolidate_remove_starting_window_from_task", "starting windows are removed once all activities draw"),
    (W + "enable_focus_reset_on_display_removal", "focus returns to the default display when an external one is unplugged"),
    (W + "enable_split_dismiss_animation_v2", "split-screen dismiss animation"),
    (W + "fix_multi_window_task_focus_change", "focus does not jump to a lower multi-window task"),
    (W + "prioritize_visible_task_display_over_source", "launch display follows the visible task"),
    (W + "reduce_window_traversal_on_entering", "fewer window traversals after enter animations"),
    (W + "remove_starting_window_when_commit_invisible", "orphaned starting windows are cleaned up"),
    (W + "report_missed_enter_anim_on_resume", "enter-animation-complete is delivered after a late attach"),
    (W + "return_windowless_root_views_in_wmglobal_getwindowview", "getWindowView finds SurfaceControlViewHost roots"),
    (W + "show_ime_layering_target_when_adding", "no IME flicker when a layering target is added"),
    (W + "update_dims_when_window_shown", "dim layers update when a window first draws"),
    (W + "use_snapshot_fixed_rotation", "snapshot starting windows use the snapshot's rotation"),
    (SH + "fix_bubble_bar_stashing_with_hardware_keyboard", "bubble bar stashes correctly with a hardware keyboard"),
    (SH + "fix_bubble_bar_visibility_update_dropped", "bubble bar visibility updates survive interrupted animations"),
    (SH + "fix_bubbles_stack_visible_in_immersive", "bubble stack hidden in immersive mode"),
    (S + "async_notification_launch_ipc", "notification clicks do their binder calls off the main thread"),
    (S + "clipboard_overlay_multiuser", "clipboard overlay uses the current user's context"),
    (S + "enable_compose_external_display_dialog", "Compose dialog for connecting an external display"),
    (S + "fix_predictive_back_clipping", "predictive-back animation clipping with a pinned taskbar"),
    (S + "floating_menu_adjust_cutout_avoidance", "accessibility floating menu placement"),
    (S + "handle_boot_completed_on_separate_thread", "SystemUI handles LOCKED_BOOT_COMPLETED off the main thread"),
    (S + "nesteddraggable_gesture_pickup", "shade drag gesture pickup in NestedDraggable"),
    (S + "nssl_touch_dispatch_fix", "notification list sends whole touch streams to Compose (scene container is on)"),
    (S + "qs_cast_tile_skip_wifi_check", "Cast tile also works on Ethernet"),
    (S + "stl_fling_animation_consume_overshoot", "shade fling animation handles overshoot"),
    (S + "wakefulness_events_shared_flow", "PowerInteractor wakefulness events as a SharedFlow"),
    (S + "wakefulness_for_animations", "keyguard animations use the right wakefulness signal"),
    (L + "enable_drag_start_end_multi_dispatch", "Launcher drag start/end reach every listener"),
    ("com.android.graphics.surfaceflinger.flags.hwc_buffer_override_skip", "SurfaceFlinger buffer-override check includes non-client layers"),
    ("com.android.media.flags.make_device_selection_behaviour_respect_route_listing_preference", "media output switcher honours RouteListingPreference"),
    ("com.android.media.flags.move_output_switcher_calls_to_background_thread", "media output switcher off the main thread"),
    ("com.android.server.accessibility.enable_magnification_hide_settings_button_in_temporary_mode", "magnification settings button"),
    ("com.android.server.accessibility.fix_full_screen_magnification_event_time_corruption", "full-screen magnification event times"),
    ("com.android.server.accessibility.send_hover_exit_on_gesture_interruption", "touch exploration hover exit"),
    ("android.view.accessibility.fix_a11y_lock_screen_jank", "accessibility lock transition"),
    ("android.view.inputmethod.set_self_visibility_only_once", "IME visibility set once"),
    ("android.content.res.resources_manager_cache_leak_cleanup", "ResourcesManager frees expired resource impls (memory leak)"),
    ("android.app.metric_value_alternative_strings", "notification metric values pick a fitting format (10,000 / 10k)"),
    ("android.service.dreams.drive_dream_state_from_occlusion", "dream state from WM occlusion (race fix)"),
]
for f, r in G5:
    d("bugfix", "enable", "5", r, f)
for f in ["com.android.graphics.libgui.flags.allocate_buffer_priority_inheritance", "android.location.flags.use_settings_main_switch_for_scanning"]:
    d("bugfix", "skip", "-", NOOP, f)
d("bugfix", "skip", "-", "already on: ANAL-206 (B5) enables it in release/openbook/ (no screenshot shutter sound unless "
  "forced); not duplicated in this value set", S + "screenshot_remove_nonforced_sound")

# ---- Group 6: internal refactors and performance Googlebook ships (no intended visible change)
d("platform", "enable", "6", "task snapshots: only low-res cached in system_server (memory)", W + "only_cache_low_res_task_snapshot")
d("platform", "enable", "6", "one-off transition handlers get their own leashes", SH + "add_one_off_handler_leashes")
d("platform", "defer", "-", "untested on its own: taken out of v3 while the empty shade was bisected, which turned out to be "
  "start_on_gone_scene_if_no_lockscreen; it moves every @Main coroutine in SystemUI to Compose's AndroidUiDispatcher, "
  "so retest it alone", S + "use_android_ui_dispatcher")
d("platform", "enable", "6", "status bar touch forwarding from Compose (scene container is on)", S + "status_bar_event_forwarding_modernization")
d("platform", "enable", "6", "taskbar runs on its own UI thread", L + "enable_taskbar_ui_thread")
d("platform", "enable", "6", "Launcher model binds through repositories (model_repository and simplified binding are on)",
  L + "bind_model_using_repository")

# ---- Not applicable
NA = {
    "telephony / modem (OpenBook laptops have none)": [
        "com.android.internal.telephony.flags." + n for n in [
            "downloadable_subscription_include_carrier_identifier_internal", "enable_ons_cleanup", "enforce_emergency_exit_multi_call",
            "fix_sql_injection_hbpcd", "ignore_incall_mmi_for_emergency", "init_rcs_provisioning_monitor_async", "new_satellite_icon",
            "offload_startup_binder_calls", "ons_handler_thread", "satellite_data_metrics_enhancement", "support_same_uri_conference_srvcc"]]
        + ["com.android.settings.flags.enable_satellite_toggle", "com.android.server.notification.favorites_incoming_call_lights"],
    "headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not": [
        "android.multiuser.hsu_allowlist_activities", "android.multiuser.hsu_allowlist_notifications", "android.multiuser.hsu_app_management",
        "android.multiuser.hsu_device_provisioner", "android.multiuser.hsu_disable_notifications", S + "hsu_qs_changes",
        S + "floating_menu_on_headless_user", "android.os.login_add_user_enforcement"],
    "Wear / watch sync": ["com.android.server.connectivity.sync_airplane_mode_with_watches"],
    "needs a vibrator (phones)": ["android.media.audio.enable_ringtone_haptics_customization",
                                  "com.android.server.notification.notification_vibration_in_sound_uri"],
    "work profile / device-owner (DPC) only; OpenBook ships no DPC": [
        "android.app.admin.flags.add_user_info_in_profile_off_deadline_alarm", "android.app.admin.flags.check_personal_suspension_for_all_profiles",
        "android.app.admin.flags.use_hardened_frp_active_check", "com.android.server.usb.flags.enable_camera_policy_check"],
    "Google supervision (Family Link) app": ["android.app.supervision.flags.enable_remove_device_admin_checks_for_reset_password_token",
                                            "android.app.supervision.flags.enable_supported_apps_retrieval_updates"],
    "AI/agent services OpenBook does not have (computer control, contextual search, attention, summaries, Magic Pointer)": [
        "android.companion.virtualdevice.flags.computer_control_access", "android.companion.virtualdevice.flags.computer_control_support_v5",
        "android.app.contextualsearch.flags.include_audio_playing_status", "com.android.input.flags.enable_attention_service_apis",
        S + "notification_summarization_allow_animation", "com.android.hardware.input.enable_contextual_cursor_desktop_entrypoints",
        L + "enable_cue_bar_desktop_form_factor", "android.app.enable_automation_notification_ui"],
    "tablet hub / dream switcher": ["android.service.dreams.dreams_switcher", "android.service.dreams.dreams_switcher_edge_swipe_enabled",
                                   "android.service.dreams.dreams_switcher_long_press_enabled", S + "upright_charging_dreams_setup"],
    "MTP device (gadget) mode; a laptop is the USB host": ["android.hardware.usb.flags.mtp_download_io_order_improvement",
                                                          "android.hardware.usb.flags.mtp_ffs_handle_close_concurrency_fix"],
    "setup wizard / Google services UI we do not ship": ["com.android.server.accessibility.enable_color_daltonizer_in_suw",
                                                        "com.android.settings.flags.enable_binary_transparency_in_safety_center"],
    "legacy hardware activity recognition; no such sensor": ["android.location.flags.disable_hardware_ar"],
    "bootloader reads flags from misc; OpenBook boots through UEFI/GRUB": ["com.android.aconfig_new_storage.enable_bootloader_sync"],
    "digital-wellbeing distracting-app interception; no wellbeing app": [W + "activity_start_interceptor_speedbumps"],
    "fixes flaky backup tests only": ["com.android.server.backup.enable_synchronous_restore_session_cleanup"],
}
for reason, fl in NA.items():
    cat = "bugfix" if reason.startswith("fixes") else "n/a"
    for f in fl:
        d("n/a", "skip", "-", reason, f)

for f in ["com.android.wallpaper.enable_effect_for_cat_smile", "com.android.settings.flags.owl_v2_enabled",
          "com.android.media.audio.camera_shutter_sound", "com.android.hardware.input.enable_poem_input_customization",
          "android.hardware.usb.flags.enable_usb_dp_upstream_irq", "android.hardware.usb.flags.enable_usbdp_utils_library",
          "com.android.server.adb.flags.use_pairing_server_v2", "android.multiuser.user_removal_minor_apis_2026",
          "android.app.admin.flags.introduce_generic_provisioning_error", "com.android.graphics.libgui.flags.wb_ring_buffer"]:
    d("n/a" if "cat_smile" in f or "owl" in f or "camera_shutter" in f else "platform", "skip", "-", NOOP, f)

# ---- Platform: deferred (no desktop-visible change; needs its own test, hardware or owner input)
DEFER = {
    "process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass": [
        "com.android.server.am." + n for n in [
            "enable_capability_controller_computation", "encapsulate_cur_oom_adj", "encapsulate_cur_proc_state",
            "explicit_cpu_capability_for_top_processes", "set_initial_oom_score_adj", "set_initial_oom_score_adj_for_type_added_application",
            "set_initial_oom_score_adj_for_type_broadcast", "set_initial_oom_score_adj_for_type_link_failed",
            "set_initial_oom_score_adj_for_type_on_hold"]],
    "graphics pipeline change; test on the G14 (drm_hwcomposer, 890M) rather than the VM": [
        "com.android.graphics.surfaceflinger.flags.graphite_renderengine_preview_rollout",
        "com.android.graphics.surfaceflinger.flags.wb_framebuffersurface2", "com.android.graphics.surfaceflinger.flags.modeset_multi_display",
        "com.android.graphics.surfaceflinger.flags.mirror_with_crop", "android.view.flags.toolkit_disable_category_on_mrr"],
    "adaptive-refresh-rate panels only (Pixel ARR)": ["com.android.graphics.surfaceflinger.flags.use_last_vsync_predict"],
    "laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light)": [
        "android.hardware.usb.flags.enable_pci_tunnel_control", "android.hardware.usb.flags.enable_persistent_usb_device_permissions",
        "com.android.server.usb.flags.wait_for_alsa_scan_results_if_has_audio_interface",
        "com.android.server.power.optimization.x86_cpu_energy_attribution",
        "com.android.server.display.feature.flags.smart_adaptive_brightness", "com.android.btaudio.hal.flags.leaudio_iso_parameter_update"],
    "multi-user policy; revisit with multi-user support": [
        "android.multiuser.dont_show_other_users_apps_to_admin", "android.multiuser.enable_explicit_static_overlay_allowlisting",
        "android.multiuser.user_filter_refactoring", "android.os.disallow_add_guest"],
    "enterprise policy refactor across 57 files; no DPC to exercise it": ["android.app.admin.flags.policy_transparency_refactor_enabled"],
    "boot-time change in system_server; measure with boot timing separately": ["com.android.server.flags.parallelize_onbootphase"],
    "kernel-dependent (binder netlink); check the G14 and Cuttlefish kernels first": ["android.os.binder_netlink_enabled"],
    "Settings preference-framework migration (battery screens); no desktop change": ["com.android.settings.flags.catalyst_migration_26q3"],
    "accessibility feature, not a desktop change; take with an accessibility pass": ["android.view.accessibility.enable_captions_easy_reader"],
}
for reason, fl in DEFER.items():
    for f in fl:
        d("platform", "defer", "-", reason, f)

DIAG = ("diagnostics, logging or metrics only; no user-visible change", [
    "android.app.backup_restore_logging", "android.location.flags.location_auditing", "android.tracing.protolog_auto_clear_incremental_state",
    "com.android.server.am.enable_long_method_tracing_on_anr_timer", "com.android.server.utils.long_method_trace",
    W + "enable_input_dispatcher_long_method_tracing", L + "enable_recents_window_proto_log", L + "enable_state_manager_proto_log",
    "com.android.server.stats.add_webview_pin_quota_puller", "com.android.server.ui_latency_stats.ui_latency_stats_service",
    "perfetto.flags.use_unix_socket_inotify"])
for f in DIAG[1]:
    d("platform", "skip", "-", DIAG[0], f)
MISC = {
    "platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL)": [
        "android.security.enable_service_side_credential_type_cache", "com.android.libsnapshot.memory_efficient_data_structures",
        "com.android.server.deviceidle.support_allow_while_idle_quota_zero", "com.android.server.display.feature.flags.refactor_persistent_data_store",
        W + "screen_capture_exclusion_flags", "suspend_service.flags.enable_pm_fs_abort", "com.android.hardware.input.hid_api"],
}
for reason, fl in MISC.items():
    for f in fl:
        d("platform", "defer", "-", reason, f)


def main():
    rows = [l.split("\t") for l in open(sys.argv[1]).read().splitlines()]
    hdr, rows = rows[0], rows[1:]
    ix = {h: i for i, h in enumerate(hdr)}
    seen = set()
    print("flag\tcontainer\tpurpose\treaders\tcategory\tdecision\tgroup\treason\tdescription")
    for r in sorted(rows, key=lambda r: (D[r[0]][2] if D[r[0]][2] != "-" else "9", r[0])):
        f = r[0]
        cat, dec, grp, reason = D[f]
        if reason == NOOP:
            assert r[ix["gating"]] == "0", f
        else:
            assert r[ix["gating"]] != "0" or dec != "enable", f
        seen.add(f)
        print("\t".join([f, r[ix["container"]], r[ix["purpose"]].replace("(default)", ""), r[ix["gating"]], cat, dec, grp, reason,
                         r[ix["description"]]]))
    extra = set(D) - seen
    assert not extra, extra
    assert len(seen) == 218, len(seen)


main()
