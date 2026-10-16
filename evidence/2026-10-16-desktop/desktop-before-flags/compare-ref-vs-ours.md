# Desktop comparison

- Reference: `google/sdk_gdesktop_x86_64/emu64xa:17/CLE1.260506.004/15373846:userdebug/test-keys`
- Ours: `AnyBook/anybook_cf_x86_64_pc/vsoc_x86_64_only:17/CP2A.260605.016/eng.builde:userdebug/test-keys`

## pm list features

- Only in reference (11): `feature:android.hardware.faketouch`, `feature:android.hardware.fingerprint`, `feature:android.hardware.identity_credential=202301`, `feature:android.hardware.sensor.accelerometer`, `feature:android.hardware.sensor.compass`, `feature:android.hardware.touchscreen`, `feature:android.hardware.touchscreen.multitouch`, `feature:android.hardware.touchscreen.multitouch.distinct`, `feature:android.hardware.touchscreen.multitouch.jazzhand`, `feature:android.software.midi`, `feature:reqGlEsVersion=0x30000`
- Only in ours (6): `feature:android.hardware.camera.autofocus`, `feature:android.hardware.ethernet`, `feature:android.hardware.usb.accessory`, `feature:android.hardware.usb.host`, `feature:android.software.device_id_attestation`, `feature:reqGlEsVersion=0x30001`
- In both: 73

## System properties: desktop, window, UI shell and graphics: 38 differences

| key | reference | ours |
|---|---|---|
| `debug.angle.feature_overrides_enabled` | `—` | `mapUnspecifiedColorSpaceToPassThrough` |
| `debug.hwui.renderer` | `skiagl` | `skiavk` |
| `debug.renderengine.backend` | `skiaglthreaded` | `—` |
| `debug.sf.nobootanimation` | `1` | `—` |
| `qemu.sf.lcd_density` | `160` | `—` |
| `ro.boot.cpuvulkan.version` | `—` | `0` |
| `ro.boot.debug.hwui.renderer` | `skiagl` | `—` |
| `ro.boot.hardware.angle_feature_overrides_enabled` | `—` | `mapUnspecifiedColorSpaceToPassThrough` |
| `ro.boot.hardware.egl` | `—` | `angle` |
| `ro.boot.hardware.gltransport` | `pipe` | `virtio-gpu-asg` |
| `ro.boot.hardware.gralloc` | `—` | `minigbm` |
| `ro.boot.hardware.guest_hwui_renderer` | `—` | `skiavk` |
| `ro.boot.hardware.hwcomposer` | `—` | `ranchu` |
| `ro.boot.hardware.hwcomposer.display_finder_mode` | `—` | `drm` |
| `ro.boot.hardware.hwcomposer.display_framebuffer_format` | `—` | `rgba` |
| `ro.boot.lcd_density` | `—` | `160` |
| `ro.boot.opengles.version` | `196608` | `196609` |
| `ro.boot.qemu.cpuvulkan.version` | `4210688` | `—` |
| `ro.boot.qemu.gltransport.drawFlushInterval` | `800` | `—` |
| `ro.boot.qemu.gltransport.name` | `pipe` | `—` |
| `ro.cpuvulkan.version` | `4210688` | `0` |
| `ro.dalvik.vm.native.bridge` | `libndk_translation.so` | `0` |
| `ro.enable.native.bridge.exec` | `1` | `—` |
| `ro.hardware.egl` | `emulation` | `angle` |
| `ro.hardware.gralloc` | `ranchu` | `minigbm` |
| `ro.hardware.hwcomposer` | `—` | `ranchu` |
| `ro.launcher.depth.widget` | `—` | `0` |
| `ro.opengles.version` | `196608` | `196609` |
| `ro.sf.lcd_density` | `—` | `160` |
| `ro.surface_flinger.has_HDR_display` | `false` | `—` |
| `ro.surface_flinger.has_wide_color_display` | `false` | `—` |
| `ro.surface_flinger.protected_contents` | `false` | `—` |
| `ro.surface_flinger.running_without_sync_framework` | `—` | `true` |
| `ro.surface_flinger.use_color_management` | `false` | `—` |
| `ro.vendor.hwcomposer.display_finder_mode` | `—` | `drm` |
| `ro.vendor.hwcomposer.display_framebuffer_format` | `—` | `rgba` |
| `ro.vendor.hwcomposer.pmem` | `—` | `/dev/block/pmem1` |
| `ro.vulkan.apex` | `—` | `com.google.cf.vulkan` |

## System properties: all (identity, network and per-boot props skipped): 220 differences

| key | reference | ours |
|---|---|---|
| `aaudio.hw_burst_min_usec` | `—` | `2000` |
| `aaudio.mmap_exclusive_policy` | `—` | `2` |
| `aaudio.mmap_policy` | `—` | `2` |
| `dalvik.vm.heapsize` | `576m` | `512m` |
| `dalvik.vm.heapstartsize` | `8m` | `16m` |
| `dalvik.vm.isa.x86_64.variant` | `x86_64` | `silvermont` |
| `debug.angle.feature_overrides_enabled` | `—` | `mapUnspecifiedColorSpaceToPassThrough` |
| `debug.c2.use_dmabufheaps` | `—` | `1` |
| `debug.hwui.renderer` | `skiagl` | `skiavk` |
| `debug.renderengine.backend` | `skiaglthreaded` | `—` |
| `debug.sf.nobootanimation` | `1` | `—` |
| `debug.stagefright.ccodec` | `4` | `—` |
| `debug.tracing.battery_stats.wifi` | `1` | `—` |
| `debug.tracing.battery_stats.wifi_radio` | `1` | `—` |
| `debug.tracing.battery_stats.wifi_scan` | `1` | `—` |
| `debug.tracing.battery_stats.wifi_signal_strength` | `4` | `—` |
| `debug.tracing.battery_stats.wifi_suppl` | `10` | `—` |
| `drm.service.enabled` | `—` | `true` |
| `graphics.gpu.profiler.support` | `false` | `—` |
| `hidl_memory.disabled` | `—` | `true` |
| `hwservicemanager.disabled` | `false` | `true` |
| `hwservicemanager.ready` | `true` | `—` |
| `hypervisor.memory_reclaim.supported` | `—` | `1` |
| `input_device.config_file.apex` | `—` | `com.google.cf.input.config` |
| `kcmdline.binder` | `—` | `unset` |
| `kcmdline.loaded` | `—` | `1` |
| `ota.warm_reset` | `—` | `0` |
| `partition.odm.verified` | `—` | `2` |
| `partition.odm.verified.check_at_most_once` | `—` | `0` |
| `partition.odm.verified.hash_alg` | `—` | `sha256` |
| `partition.odm.verified.root_digest` | `—` | `799e2ba0af95501fa7b3ef0b8177ae08286e2f702ec8319c3b1819a66f4c9b1a` |
| `partition.odm_dlkm.verified` | `—` | `2` |
| `partition.odm_dlkm.verified.check_at_most_once` | `—` | `0` |
| `partition.odm_dlkm.verified.hash_alg` | `—` | `sha256` |
| `partition.odm_dlkm.verified.root_digest` | `—` | `1364f550dfae8394d11cb08dc2ad75ed84b5a360cfacf1c7e6c35f4bf956c584` |
| `partition.product.verified` | `—` | `2` |
| `partition.product.verified.check_at_most_once` | `—` | `0` |
| `partition.product.verified.hash_alg` | `—` | `sha256` |
| `partition.product.verified.root_digest` | `—` | `b79518729407bd73dda79df3a37d64eaf5500f5e278174b1e84769f688b812f8` |
| `partition.system.verified.root_digest` | `facaad072701f19155cf2005fd01ffc877d850f59f85baae1b601fc679d01244` | `cb544f547b07d846e549afd0cfdcd90c844b985fdf8bdd5bca74146fdf09a8bc` |
| `partition.system_dlkm.verified` | `—` | `2` |
| `partition.system_dlkm.verified.check_at_most_once` | `—` | `0` |
| `partition.system_dlkm.verified.hash_alg` | `—` | `sha256` |
| `partition.system_dlkm.verified.root_digest` | `—` | `3f2663d698ea0b64025baeda7c8aee3482d6c3242c7939b91029250ad10dd3c0` |
| `partition.system_ext.verified` | `—` | `2` |
| `partition.system_ext.verified.check_at_most_once` | `—` | `0` |
| `partition.system_ext.verified.hash_alg` | `—` | `blake2b-256` |
| `partition.system_ext.verified.root_digest` | `—` | `64b7f189be42ddf825db31b4bc07b2052d1c967dad6ca49aadbfcfecc54a1a53` |
| `partition.vendor.verified` | `—` | `2` |
| `partition.vendor.verified.check_at_most_once` | `—` | `0` |
| `partition.vendor.verified.hash_alg` | `—` | `sha256` |
| `partition.vendor.verified.root_digest` | `—` | `288c71ed2defe52037f08babdf4dc77255da7b8f49b20edd1f12f23d37b2e828` |
| `partition.vendor_dlkm.verified` | `—` | `2` |
| `partition.vendor_dlkm.verified.check_at_most_once` | `—` | `0` |
| `partition.vendor_dlkm.verified.hash_alg` | `—` | `sha256` |
| `partition.vendor_dlkm.verified.root_digest` | `—` | `b5dfae4dec8535e1c635935354a66543a8985b1a1eb199d3c6f22c320fd5bbc1` |
| `persist.netd.stable_secret` | `5149:fa14:c09e:9dd2:7e01:f1e1:94aa:32e0` | `—` |
| `persist.sys.disable_rescue` | `true` | `—` |
| `persist.sys.fuse.passthrough.enable` | `—` | `true` |
| `persist.sys.timezone` | `America/New_York` | `GMT` |
| `qemu.hw.mainkeys` | `0` | `—` |
| `qemu.sf.lcd_density` | `160` | `—` |
| `remote_provisioning.hostname` | `remoteprovisioning.googleapis.com` | `preprod-remoteprovisioning.googleapis.com` |
| `remote_provisioning.tee.rkp_only` | `—` | `1` |
| `ro.audio.ihaladaptervendorextension_enabled` | `—` | `true` |
| `ro.berberis.flags` | `accurate-sigsegv` | `—` |
| `ro.berberis.version` | `16.0.0` | `—` |
| `ro.board.platform` | `` | `vsoc_x86_64` |
| `ro.boot.auto_eth_guest_addr` | `—` | `192.168.98.3` |
| `ro.boot.boot_devices` | `pci0000:00/0000:00:03.0 pci0000:00/0000:00:06.0` | `pci0000:00/0000:00:13.0, pci0000:00/0000:00:14.0` |
| `ro.boot.cpuvulkan.version` | `—` | `0` |
| `ro.boot.dalvik.vm.heapsize` | `576m` | `—` |
| `ro.boot.ddr_size` | `—` | `9830MB` |
| `ro.boot.debug.hwui.renderer` | `skiagl` | `—` |
| `ro.boot.debug.sf.nobootanimation` | `1` | `—` |
| `ro.boot.enable_bootanimation` | `—` | `1` |
| `ro.boot.enable_confirmationui` | `—` | `1` |
| `ro.boot.flash.locked` | `—` | `0` |
| `ro.boot.force_normal_boot` | `—` | `1` |
| `ro.boot.fstab_suffix` | `—` | `cf.f2fs.hctr2` |
| `ro.boot.hardware` | `ranchu` | `cutf_cvm` |
| `ro.boot.hardware.angle_feature_overrides_enabled` | `—` | `mapUnspecifiedColorSpaceToPassThrough` |
| `ro.boot.hardware.egl` | `—` | `angle` |
| `ro.boot.hardware.gltransport` | `pipe` | `virtio-gpu-asg` |
| `ro.boot.hardware.gralloc` | `—` | `minigbm` |
| `ro.boot.hardware.guest_disable_renderer_preload` | `—` | `true` |
| `ro.boot.hardware.guest_hwui_renderer` | `—` | `skiavk` |
| `ro.boot.hardware.hwcomposer` | `—` | `ranchu` |
| `ro.boot.hardware.hwcomposer.display_finder_mode` | `—` | `drm` |
| `ro.boot.hardware.hwcomposer.display_framebuffer_format` | `—` | `rgba` |
| `ro.boot.hw_timeout_multiplier` | `—` | `3` |
| `ro.boot.hypervisor.protected_vm.supported` | `—` | `0` |
| `ro.boot.hypervisor.version` | `—` | `cf-crosvm` |
| `ro.boot.hypervisor.vm.supported` | `—` | `1` |
| `ro.boot.lcd_density` | `—` | `160` |
| `ro.boot.logcat` | `*:V` | `—` |
| `ro.boot.modem_simulator_ports` | `—` | `9600` |
| `ro.boot.opengles.version` | `196608` | `196609` |
| `ro.boot.openthread_node_id` | `—` | `1` |
| `ro.boot.qemu` | `1` | `—` |
| `ro.boot.qemu.adb.pubkey` | `QAAAAA8tCGER3n4W+Vw8rLQ2qiNH5vb7QBeoYm20VkjXYzu1l+0kDb/79EsPQD9TMnpLn+mUTzQNO7HZ` | `—` |
| `ro.boot.qemu.avd_name` | `anybook-desktop-ref` | `—` |
| `ro.boot.qemu.camera_hq_edge_processing` | `0` | `—` |
| `ro.boot.qemu.camera_protocol_ver` | `1` | `—` |
| `ro.boot.qemu.cpuvulkan.version` | `4210688` | `—` |
| `ro.boot.qemu.gltransport.drawFlushInterval` | `800` | `—` |
| `ro.boot.qemu.gltransport.name` | `pipe` | `—` |
| `ro.boot.qemu.hwcodec.avcdec` | `2` | `—` |
| `ro.boot.qemu.hwcodec.hevcdec` | `2` | `—` |
| `ro.boot.qemu.hwcodec.vpxdec` | `2` | `—` |
| `ro.boot.qemu.settings.system.screen_off_timeout` | `2147483647` | `—` |
| `ro.boot.qemu.skin` | `1920x1080` | `—` |
| `ro.boot.qemu.virtiowifi` | `1` | `—` |
| `ro.boot.qemu.vsync` | `60` | `—` |
| `ro.boot.serialconsole` | `—` | `0` |
| `ro.boot.setupwizard_mode` | `—` | `DISABLED` |
| `ro.boot.slot_suffix` | `—` | `_a` |
| `ro.boot.vendor.apex.com.android.hardware.gatekeeper` | `—` | `com.android.hardware.gatekeeper.nonsecure` |
| `ro.boot.vendor.apex.com.android.hardware.graphics.composer` | `—` | `com.android.hardware.graphics.composer.ranchu` |
| `ro.boot.vendor.apex.com.android.hardware.keymint` | `—` | `com.android.hardware.keymint.rust_nonsecure` |
| `ro.boot.vendor.apex.com.android.hardware.secure_element` | `—` | `com.android.hardware.secure_element` |
| `ro.boot.vendor.apex.com.android.hardware.strongbox` | `—` | `none` |
| `ro.boot.vendor.apex.com.android.hardware.weaver` | `—` | `none` |
| `ro.boot.vendor.apex.com.google.cf.disabled` | `—` | `none` |
| `ro.boot.vendor.apex.com.google.emulated.camera.provider.hal` | `—` | `com.google.emulated.camera.provider.hal` |
| `ro.boot.vendor.audiocontrol.server.cid` | `—` | `3` |
| `ro.boot.vendor.audiocontrol.server.port` | `—` | `9410` |
| `ro.boot.verifiedbootstate` | `—` | `orange` |
| `ro.boot.vhal_proxy_server_port` | `—` | `9300` |
| `ro.boot.vsock_lights_cid` | `—` | `3` |
| `ro.boot.vsock_lights_port` | `—` | `6900` |
| `ro.boot.vsock_tombstone_port` | `—` | `6600` |
| `ro.boot.wifi_impl` | `—` | `mac80211_hwsim_virtio` |
| `ro.boot.wifi_mac_prefix` | `—` | `5554` |
| `ro.build.ab_update` | `none` | `true` |
| `ro.build.product` | `emu64xa` | `vsoc_x86_64_only` |
| `ro.build.version.security_patch` | `2026-05-05` | `2026-06-05` |
| `ro.camerax.extensions.enabled` | `—` | `true` |
| `ro.com.google.locationfeatures` | `—` | `1` |
| `ro.cp_system_other_odex` | `0` | `1` |
| `ro.cpuvulkan.version` | `4210688` | `0` |
| `ro.crypto.dm_default_key.options_format.version` | `2` | `—` |
| `ro.crypto.metadata_init_delete_all_keys.enabled` | `—` | `true` |
| `ro.crypto.volume.filenames_mode` | `aes-256-cts` | `—` |
| `ro.dalvik.vm.isa.arm` | `x86` | `—` |
| `ro.dalvik.vm.isa.arm64` | `x86_64` | `—` |
| `ro.dalvik.vm.native.bridge` | `libndk_translation.so` | `0` |
| `ro.enable.native.bridge.exec` | `1` | `—` |
| `ro.fstype.data` | `ext4` | `f2fs` |
| `ro.hardware` | `ranchu` | `cutf_cvm` |
| `ro.hardware.audio.primary` | `—` | `goldfish` |
| `ro.hardware.audio.tinyalsa.host_latency_ms` | `80` | `—` |
| `ro.hardware.audio.tinyalsa.period_count` | `4` | `—` |
| `ro.hardware.audio.tinyalsa.period_size_multiplier` | `2` | `—` |
| `ro.hardware.egl` | `emulation` | `angle` |
| `ro.hardware.gralloc` | `ranchu` | `minigbm` |
| `ro.hardware.hwcomposer` | `—` | `ranchu` |
| `ro.hardware.keystore_desede` | `—` | `true` |
| `ro.hardware.power` | `ranchu` | `—` |
| `ro.hw_timeout_multiplier` | `—` | `3` |
| `ro.incremental.enable` | `yes` | `1` |
| `ro.launcher.depth.widget` | `—` | `0` |
| `ro.minui.pixel_format` | `—` | `ABGR_8888` |
| `ro.misctrl.16kb_before` | `—` | `0` |
| `ro.nnapi.extensions.deny_on_product` | `true` | `—` |
| `ro.oem_unlock_supported` | `—` | `1` |
| `ro.opengles.version` | `196608` | `196609` |
| `ro.product.ab_ota_partitions` | `—` | `boot,init_boot,odm,odm_dlkm,product,system,system_dlkm,system_ext,vbmeta,vbmeta_` |
| `ro.product.board` | `goldfish_x86_64` | `cutf` |
| `ro.product.brand` | `google` | `AnyBook` |
| `ro.product.device` | `emu64xa` | `vsoc_x86_64_only` |
| `ro.product.first_api_level` | `36` | `37` |
| `ro.product.model` | `Android Desktop` | `AnyBook Cuttlefish x86_64 desktop` |
| `ro.product.name` | `sdk_gdesktop_x86_64` | `anybook_cf_x86_64_pc` |
| `ro.rebootescrow.device` | `—` | `/dev/block/pmem0` |
| `ro.setupwizard.mode` | `—` | `DISABLED` |
| `ro.sf.lcd_density` | `—` | `160` |
| `ro.soc.manufacturer` | `AOSP` | `Google` |
| `ro.soc.model` | `ranchu` | `vsoc_x86_64_only` |
| `ro.surface_flinger.has_HDR_display` | `false` | `—` |
| `ro.surface_flinger.has_wide_color_display` | `false` | `—` |
| `ro.surface_flinger.protected_contents` | `false` | `—` |
| `ro.surface_flinger.running_without_sync_framework` | `—` | `true` |
| `ro.surface_flinger.use_color_management` | `false` | `—` |
| `ro.vendor.api_level` | `202504` | `202604` |
| `ro.vendor.boot_security_patch` | `—` | `2026-06-05` |
| `ro.vendor.hwc.drm.present_fence_not_reliable` | `—` | `true` |
| `ro.vendor.hwcomposer.display_finder_mode` | `—` | `drm` |
| `ro.vendor.hwcomposer.display_framebuffer_format` | `—` | `rgba` |
| `ro.vendor.hwcomposer.pmem` | `—` | `/dev/block/pmem1` |
| `ro.vendor.init_dev_config.path` | `—` | `/vendor/bin/init_dev_config` |
| `ro.vendor.uwb.dev` | `/dev/hvc2` | `/dev/hvc9` |
| `ro.virtual_ab.batch_writes` | `—` | `true` |
| `ro.virtual_ab.compression.enabled` | `—` | `true` |
| `ro.virtual_ab.compression.threads` | `—` | `true` |
| `ro.virtual_ab.compression.xor.enabled` | `—` | `true` |
| `ro.virtual_ab.enabled` | `—` | `true` |
| `ro.virtual_ab.io_uring.enabled` | `—` | `true` |
| `ro.virtual_ab.ublk.enabled` | `—` | `true` |
| `ro.virtual_ab.userspace.snapshots.enabled` | `—` | `true` |
| `ro.vulkan.apex` | `—` | `com.google.cf.vulkan` |
| `ro.zygote.disable_gl_preload` | `1` | `true` |
| `service.bootanim.progress` | `90` | `0` |
| `service.sf.prime_shader_cache` | `—` | `0` |
| `sys.cppreopt` | `—` | `finished` |
| `sys.system_server.start_elapsed` | `7122` | `4151` |
| `sys.system_server.start_uptime` | `7122` | `4151` |
| `tombstoned.max_tombstone_count` | `50` | `100` |
| `vendor.camera.hal.build_id` | `—` | `eng.builde` |
| `vendor.camera.hal.ready.count` | `—` | `1` |
| `vendor.camera.hal.start.count` | `—` | `1` |
| `vendor.camera.hal.version` | `—` | `2147480019` |
| `vendor.hwc.drm.device` | `—` | `/dev/dri/card0` |
| `vendor.qemu.sf.fake_camera` | `back` | `—` |
| `vendor.qemu.timezone` | `America/New_York` | `—` |
| `vendor.qemu.vport.bluetooth` | `/dev/vport7p3` | `—` |
| `vendor.qemu.vport.uwb` | `/dev/vport7p2` | `—` |
| `vendor.ser.bt-uart` | `—` | `/dev/hvc5` |
| `vendor.wlan.driver.version` | `1.0` | `—` |
| `vendor.wlan.firmware.version` | `1.0` | `—` |

## aconfig flags matching /desktop|freeform|taskbar|windowing|desk_|display_content_mode|force_freeform/ (aflags list): 12 differences

| key | reference | ours |
|---|---|---|
| `android.view.inputmethod.ime_switcher_menu_systemui_style_update_desktop` | `enabled` | `—` |
| `com.android.documentsui.flags.desktop_file_handling_ro` | `enabled` | `—` |
| `com.android.documentsui.flags.desktop_ux_phase_2_ro` | `enabled` | `—` |
| `com.android.launcher3.enable_scalability_for_desktop_experience` | `enabled` | `—` |
| `com.android.launcher3.enable_taskbar_drag_and_drop` | `enabled` | `—` |
| `com.android.launcher3.orientation_friendly_desktop_grid_spec` | `enabled` | `—` |
| `com.android.providers.media.flags.enable_photopicker_desktop` | `enabled` | `disabled` |
| `com.android.systemui.desktop_effects_qs_tile` | `enabled` | `—` |
| `com.android.systemui.desktop_sizing` | `enabled` | `—` |
| `com.android.systemui.status_bar_for_desktop` | `enabled` | `—` |
| `com.android.window.flags.enable_overflow_button_for_taskbar_pinned_items` | `enabled` | `—` |
| `com.android.window.flags.show_home_behind_desktop` | `enabled` | `—` |

## Enabled overlays (cmd overlay list)

- Only in reference (4): `android: com.android.internal.ranchu.commonoverlay`, `com.android.connectivity.resources: com.android.connectivity.resources.goldfish.overlay`, `com.android.systemui: com.android.systemui.auto_generated_rro_vendor__`, `com.android.uwb.resources: com.android.uwb.resources.goldfish.overlay`
- Only in ours (9): `android: android.cuttlefish.overlay`, `android: dev.anybook.overlay.desktop.framework`, `com.android.connectivity.resources: com.android.connectivity.resources.cuttlefish.overlay`, `com.android.networkstack.tethering: com.android.networkstack.tethering.cuttlefishoverlay`, `com.android.nfc: com.android.nfc.cuttlefish.overlay`, `com.android.providers.settings: com.android.providers.settings.cuttlefish.overlay`, `com.android.systemui: dev.anybook.overlay.desktop.systemui`, `com.android.uwb.resources: com.android.uwb.resources.cuttlefish.overlay`, `com.android.wifi.resources: com.android.wifi.resources.cf`
- In both: 9

## Settings.Global: 8 differences

| key | reference | ours |
|---|---|---|
| `database_creation_buildid` | `CLE1.260506.004` | `CP2A.260605.016` |
| `device_name` | `Android Desktop` | `AnyBook Cuttlefish x86_64 desktop` |
| `global_color_palette_version` | `1778224697` | `1792164464` |
| `network_watchlist_last_report_time` | `1792123200000` | `1792108800000` |
| `scene_container_enabled` | `1` | `0` |
| `tether_offload_disabled` | `1` | `—` |
| `verifier_verify_adb_installs` | `0` | `—` |
| `wifi_on` | `1` | `0` |
