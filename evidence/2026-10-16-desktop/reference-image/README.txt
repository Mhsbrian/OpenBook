# Static desktop configuration in Google's AOSP Desktop (Preview) emulator image, read offline 2026-10-16.
# Source: system-images/android-37.0/android-desktop/x86_64 (x86_64-37.0_r01.zip, sha1 a56c5e2d88a0136bfa4df406157d26a6d418732f),
# super partition unpacked with lpunpack + debugfs (tools/Dockerfile.inspect). Values only; no image files are committed.

## product/etc/build.prop (desktop, window and large-screen lines)
ro.build.characteristics=desktop
ro.dalvik.vm.enable_uffd_gc=true
persist.wm.extensions.enabled=true
persist.wm.debug.force_desktop_first_on_default_display_for_testing=true
persist.wm.extensions.activity_embedding_guard_with_android_15=false
persist.settings.large_screen_opt.enabled=true

## system/build.prop native bridge
# Removed by post_process_props.py because overridden by ro.dalvik.vm.native.bridge=libndk_translation.so
#ro.dalvik.vm.native.bridge?=0
ro.dalvik.vm.native.bridge=libndk_translation.so
ro.dalvik.vm.isa.arm64=x86_64
ro.dalvik.vm.isa.arm=x86
ro.enable.native.bridge.exec=1
ro.berberis.version=16.0.0
ro.berberis.flags=accurate-sigsegv

## vendor/etc/display_settings*.xml (values)
display_settings.xml: <config identifier="0"/> <display name="local:4619827259835644672" windowingMode="5" ignoreOrientationRequest="true"/>
display_settings_app_compat.xml: <config identifier="1"/> <display name="port:0" ignoreOrientationRequest="true"/>
display_settings_freeform.xml: <config identifier="1"/> <display name="port:0" windowingMode="5" fixedToUserRotation="2"/>

## RRO packages in /product/overlay and /vendor/overlay
product/overlay/CompanionDeviceManager__desktop__auto_generated_characteristics_rro.apk
product/overlay/DisplayCutoutEmulationCorner/DisplayCutoutEmulationCornerOverlay.apk
product/overlay/DisplayCutoutEmulationDouble/DisplayCutoutEmulationDoubleOverlay.apk
product/overlay/DisplayCutoutEmulationHole/DisplayCutoutEmulationHoleOverlay.apk
product/overlay/DisplayCutoutEmulationTall/DisplayCutoutEmulationTallOverlay.apk
product/overlay/DisplayCutoutEmulationWaterfall/DisplayCutoutEmulationWaterfallOverlay.apk
product/overlay/FontNotoSerifSource/FontNotoSerifSourceOverlay.apk
product/overlay/framework-res__desktop__auto_generated_characteristics_rro.apk
product/overlay/NavigationBarMode3Button/NavigationBarMode3ButtonOverlay.apk
product/overlay/NavigationBarModeGestural/NavigationBarModeGesturalOverlay.apk
product/overlay/NotesRoleEnabled/NotesRoleEnabledOverlay.apk
product/overlay/RanchuCommonOverlay.apk
product/overlay/TelephonyProvider__desktop__auto_generated_characteristics_rro.apk
product/overlay/TeleService__desktop__auto_generated_characteristics_rro.apk
product/overlay/TransparentNavigationBar/TransparentNavigationBarOverlay.apk
product/overlay/UwbOverlay.apk
vendor/overlay/framework-res__sdk_gdesktop_x86_64__auto_generated_rro_vendor.apk
vendor/overlay/goldfish_overlay_connectivity_gsi.apk
vendor/overlay/SystemUI__sdk_gdesktop_x86_64__auto_generated_rro_vendor.apk
