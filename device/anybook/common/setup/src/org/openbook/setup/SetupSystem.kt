// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup

import android.app.time.Capabilities
import android.app.time.TimeConfiguration
import android.app.time.TimeManager
import android.app.time.TimeZoneConfiguration
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.input.InputManager
import android.icu.text.TimeZoneNames
import android.icu.util.ULocale
import android.net.Uri
import android.os.SystemProperties
import android.os.UserHandle
import android.os.UserManager
import android.provider.Settings
import android.util.Log
import android.view.InputDevice
import android.view.inputmethod.InputMethodManager
import com.android.internal.app.LocalePicker
import com.android.internal.widget.LockPatternUtils
import com.android.internal.widget.LockscreenCredential
import java.util.Locale
import kotlin.math.abs

/** Everything setup changes in the system. The permissions are in AndroidManifest.xml. */
object SetupSystem {
    const val TAG = "OpenBookSetup"

    /** The live stick's boot entries (docs/installer.md §11): the install wizard is the first screen there. */
    const val PROP_LIVE = "ro.boot.openbook.live"

    /** `androidboot.openbook.setup=skip`: unattended runs on an installed system (docs/setup.md). */
    const val PROP_SETUP = "ro.boot.openbook.setup"

    /** AOSP's setup-wizard mode. Cuttlefish sets DISABLED unless cvd gets --setupwizard_mode=OPTIONAL|REQUIRED. */
    const val PROP_SETUPWIZARD_MODE = "ro.setupwizard.mode"

    /** Written into the installed system's boot entry by the install engine (docs/installer.md §3.5). */
    const val PROP_LOCALE = "ro.boot.openbook.locale"
    const val PROP_KEYBOARD = "ro.boot.openbook.keyboard"

    private const val USER_SETUP_COMPLETE = "user_setup_complete" // Settings.Secure, @hide

    /** Why setup must not show on this boot, or null when it should. */
    fun skipReason(context: Context): String? = when {
        SystemProperties.get(PROP_LIVE) == "1" -> "live session"
        SystemProperties.get(PROP_SETUP) == "skip" -> "androidboot.openbook.setup=skip"
        SystemProperties.get(PROP_SETUPWIZARD_MODE).equals("DISABLED", ignoreCase = true) -> "ro.setupwizard.mode=DISABLED"
        isComplete(context) -> "already complete"
        else -> null
    }

    fun isComplete(context: Context): Boolean =
        Settings.Global.getInt(context.contentResolver, Settings.Global.DEVICE_PROVISIONED, 0) != 0 &&
            Settings.Secure.getInt(context.contentResolver, USER_SETUP_COMPLETE, 0) != 0

    /** What Provision does: the device is provisioned and this user's setup is complete. */
    fun markComplete(context: Context): Boolean = try {
        Settings.Global.putInt(context.contentResolver, Settings.Global.DEVICE_PROVISIONED, 1) &&
            Settings.Secure.putInt(context.contentResolver, USER_SETUP_COMPLETE, 1)
    } catch (e: SecurityException) {
        Log.e(TAG, "could not mark setup complete", e)
        false
    }

    /** Takes setup out of the home list for good (as Provision does). */
    fun disable(context: Context, activity: Class<*>) {
        context.packageManager.setComponentEnabledSetting(
            ComponentName(context, activity),
            PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP,
        )
    }

    // ---------------------------------------------------------------------------------------------- language

    /** The installer's languages (its Welcome screen), as language tags without a region. */
    val languages = listOf(
        "en", "es", "fr", "de", "it", "pt", "nl", "pl", "sv", "tr", "el", "ru", "uk", "vi", "ja", "ko", "zh-Hans",
    )

    /** [tag]'s language in its own words, e.g. "Deutsch", "中文 (简体)". */
    fun nativeName(tag: String): String {
        val l = Locale.forLanguageTag(tag)
        val name = if (l.script.isNotEmpty()) l.getDisplayName(l) else l.getDisplayLanguage(l)
        return name.replaceFirstChar { it.titlecase(l) }
    }

    /** The language entry of [locale] in [languages], or null. */
    fun languageOf(locale: Locale): String? = languages.firstOrNull {
        val l = Locale.forLanguageTag(it)
        l.language == locale.language && (l.script.isEmpty() || l.script == locale.script || locale.script.isEmpty())
    }

    /** The regions ICU knows for [language]: its most likely region first, then by name in [display]. */
    fun regionsFor(language: String, display: Locale): List<Locale> {
        val base = Locale.forLanguageTag(language)
        val likely = ULocale.addLikelySubtags(ULocale.forLocale(base)).country
        val countries = Locale.getAvailableLocales()
            .filter { it.language == base.language && it.country.length == 2 && it.variant.isEmpty() }
            .filter { base.script.isEmpty() || it.script.isEmpty() || it.script == base.script }
            .map { it.country }
            .toSortedSet()
        val list = countries.map { Locale.Builder().setLanguage(base.language).setScript(base.script).setRegion(it).build() }
            .sortedBy { countryName(it.country, display) }
        return list.sortedByDescending { it.country == likely }
    }

    /** [country]'s name (ISO 3166) in [display]'s language. */
    fun countryName(country: String, display: Locale): String =
        Locale.Builder().setRegion(country).build().getDisplayCountry(display)

    /** Applies [locale] as the system language and region at once. */
    fun applyLocale(locale: Locale): Boolean = try {
        LocalePicker.updateLocale(locale)
        true
    } catch (e: Exception) {
        Log.w(TAG, "could not apply the locale ${locale.toLanguageTag()}", e)
        false
    }

    // ---------------------------------------------------------------------------------------------- keyboard

    data class KeyboardLayoutChoice(
        val descriptor: String,
        val name: String,
        val label: String,
        val locales: List<Locale>,
        val type: String,
    )

    /** The keyboard layouts installed on the system (AOSP's InputDevices package: 57 in Android 17). */
    fun keyboardLayouts(context: Context): List<KeyboardLayoutChoice> {
        val im = context.getSystemService(InputManager::class.java) ?: return emptyList()
        return im.keyboardLayouts.map { l ->
            val locales = l.locales.let { list -> (0 until list.size()).map { list.get(it) } }
            KeyboardLayoutChoice(l.descriptor, l.descriptor.substringAfterLast('/'), l.label, locales, l.layoutType.orEmpty())
        }.sortedBy { it.label }
    }

    /** Physical keyboards with letter keys: the laptop's own keyboard and any USB or Bluetooth keyboard. */
    fun physicalKeyboards(context: Context): List<InputDevice> {
        val im = context.getSystemService(InputManager::class.java) ?: return emptyList()
        return im.inputDeviceIds.toList().mapNotNull { im.getInputDevice(it) }
            .filter { it.isFullKeyboard && !it.isVirtual && it.isEnabled }
    }

    /** The layout Android uses for [device] now (the user's choice, the device's or the input method's default). */
    fun currentLayout(context: Context, device: InputDevice): String? {
        val im = context.getSystemService(InputManager::class.java) ?: return null
        val imm = context.getSystemService(InputMethodManager::class.java) ?: return null
        val ime = imm.currentInputMethodInfo ?: return null
        return try {
            im.getKeyboardLayoutForInputDevice(device.identifier, UserHandle.myUserId(), ime, imm.currentInputMethodSubtype)
                .layoutDescriptor
        } catch (e: RuntimeException) {
            Log.w(TAG, "could not read the layout of ${device.name}", e)
            null
        }
    }

    /**
     * Sets [descriptor] on every physical keyboard, for the current input method and subtype (Android 17 keeps one
     * layout per keyboard, user, input method and subtype; Settings › Physical keyboard does the same). Each keyboard's
     * key map (.kl, such as the G14's own files from ANAL-178) stays as it is: the layout only maps keys to characters.
     * Returns how many keyboards took it.
     */
    fun applyKeyboardLayout(context: Context, descriptor: String): Int {
        val im = context.getSystemService(InputManager::class.java) ?: return 0
        val imm = context.getSystemService(InputMethodManager::class.java) ?: return 0
        val ime = imm.currentInputMethodInfo ?: return 0.also { Log.w(TAG, "no input method: keyboard layout not set") }
        var n = 0
        for (device in physicalKeyboards(context)) {
            try {
                im.setKeyboardLayoutForInputDevice(device.identifier, UserHandle.myUserId(), ime,
                    imm.currentInputMethodSubtype, descriptor)
                n++
                Log.i(TAG, "keyboard layout ${descriptor.substringAfterLast('/')} on ${device.name}")
            } catch (e: RuntimeException) {
                Log.w(TAG, "could not set the layout of ${device.name}", e)
            }
        }
        return n
    }

    /** The installer's keyboard ids (androidboot.openbook.keyboard) as AOSP layout names. */
    private val installerKeyboards = mapOf(
        "us" to "keyboard_layout_english_us", "gb" to "keyboard_layout_english_uk", "de" to "keyboard_layout_german",
        "fr" to "keyboard_layout_french", "es" to "keyboard_layout_spanish", "it" to "keyboard_layout_italian",
        "br" to "keyboard_layout_brazilian", "nl" to "keyboard_layout_english_us_intl",
        "pl" to "keyboard_layout_polish", "se" to "keyboard_layout_swedish", "tr" to "keyboard_layout_turkish",
        "gr" to "keyboard_layout_greek", "ru" to "keyboard_layout_russian", "ua" to "keyboard_layout_ukrainian",
        // AOSP has no JIS or Korean layout; both keyboards type Latin letters like the US one.
        "jp" to "keyboard_layout_english_us", "kr" to "keyboard_layout_english_us",
    )

    /** The layout picked in the installer, if this system was installed with one. */
    fun installerLayoutName(): String? = installerKeyboards[SystemProperties.get(PROP_KEYBOARD, "")]

    // ---------------------------------------------------------------------------------------------- time

    data class TimeSettings(
        val canAutoTime: Boolean,
        val autoTime: Boolean,
        val canAutoZone: Boolean,
        val autoZone: Boolean,
        val canSetZone: Boolean,
    )

    fun readTime(context: Context): TimeSettings {
        val tm = context.getSystemService(TimeManager::class.java)
            ?: return TimeSettings(false, false, false, false, false)
        val t = tm.timeCapabilitiesAndConfig
        val z = tm.timeZoneCapabilitiesAndConfig
        // The settings say "automatic" even where nothing can detect (Android's default): a PC has no telephony and
        // no location time zone provider. Only a possessed capability makes the setting real.
        val canAutoTime = t.capabilities.configureAutoDetectionEnabledCapability == Capabilities.CAPABILITY_POSSESSED
        val canAutoZone = z.capabilities.configureAutoDetectionEnabledCapability == Capabilities.CAPABILITY_POSSESSED
        return TimeSettings(
            canAutoTime = canAutoTime,
            autoTime = canAutoTime && t.configuration.isAutoDetectionEnabled,
            canAutoZone = canAutoZone,
            autoZone = canAutoZone && z.configuration.isAutoDetectionEnabled,
            canSetZone = z.capabilities.setManualTimeZoneCapability == Capabilities.CAPABILITY_POSSESSED,
        )
    }

    fun setAutoTime(context: Context, on: Boolean): Boolean = timeCall(context, "automatic time") {
        it.updateTimeConfiguration(TimeConfiguration.Builder().setAutoDetectionEnabled(on).build())
    }

    fun setAutoZone(context: Context, on: Boolean): Boolean = timeCall(context, "automatic time zone") {
        it.updateTimeZoneConfiguration(TimeZoneConfiguration.Builder().setAutoDetectionEnabled(on).build())
    }

    /** Sets the time zone by hand (refused while it is detected automatically). */
    fun setTimeZone(context: Context, id: String): Boolean =
        timeCall(context, "time zone $id") { it.setManualTimeZone(id) }

    private inline fun timeCall(context: Context, what: String, block: (TimeManager) -> Boolean): Boolean {
        val tm = context.getSystemService(TimeManager::class.java) ?: return false
        return try {
            block(tm).also { if (it) Log.i(TAG, "$what: set") else Log.w(TAG, "$what: refused") }
        } catch (e: RuntimeException) {
            Log.w(TAG, "$what: failed", e)
            false
        }
    }

    fun set24Hour(context: Context, on: Boolean): Boolean = try {
        Settings.System.putString(context.contentResolver, Settings.System.TIME_12_24, if (on) "24" else "12")
    } catch (e: SecurityException) {
        Log.w(TAG, "could not set the clock format", e)
        false
    }

    data class Zone(val id: String, val city: String, val name: String, val offsetMillis: Int) {
        val offsetLabel: String
            get() {
                if (offsetMillis == 0) return "UTC"
                val m = abs(offsetMillis) / 60_000
                val sign = if (offsetMillis < 0) "−" else "+"
                return "UTC$sign${m / 60}" + if (m % 60 != 0) ":%02d".format(m % 60) else ""
            }
    }

    /** Time zones with a city, for [region] (ISO 3166) or for the whole world when null, sorted by offset and city. */
    fun zones(region: String?, display: Locale): List<Zone> {
        val names = TimeZoneNames.getInstance(ULocale.forLocale(display))
        val now = System.currentTimeMillis()
        val ids = android.icu.util.TimeZone.getAvailableIDs(
            android.icu.util.TimeZone.SystemTimeZoneType.CANONICAL_LOCATION, region, null,
        )
        return ids.map { id ->
            val tz = android.icu.util.TimeZone.getTimeZone(id)
            Zone(
                id = id,
                city = names.getExemplarLocationName(id) ?: id.substringAfterLast('/').replace('_', ' '),
                name = tz.getDisplayName(false, android.icu.util.TimeZone.LONG_GENERIC, display),
                offsetMillis = tz.getOffset(now),
            )
        }.sortedWith(compareBy({ it.offsetMillis }, { it.city }))
    }

    // ---------------------------------------------------------------------------------------------- you

    fun userName(context: Context): String = context.getSystemService(UserManager::class.java)?.userName.orEmpty()

    fun setUserName(context: Context, name: String): Boolean = try {
        context.getSystemService(UserManager::class.java)?.setUserName(name)
        true
    } catch (e: RuntimeException) {
        Log.w(TAG, "could not set the user name", e)
        false
    }

    fun hasSecureLockScreen(context: Context): Boolean =
        context.packageManager.hasSystemFeature(PackageManager.FEATURE_SECURE_LOCK_SCREEN)

    /**
     * Sets this user's screen lock to [credential] (a PIN, a password or none), replacing [previous] (none on a fresh
     * system; the credential set earlier in this setup if the user came back to change it).
     */
    fun setScreenLock(context: Context, credential: LockscreenCredential, previous: LockscreenCredential): Boolean = try {
        if (!credential.isNone) credential.validateBasicRequirements()
        LockPatternUtils(context).setLockCredential(credential, previous, UserHandle.myUserId())
    } catch (e: RuntimeException) {
        Log.w(TAG, "could not set the screen lock", e)
        false
    }

    // ---------------------------------------------------------------------------------------------- extras

    const val PKG_GMS = "com.google.android.gms"
    const val PKG_GSF = "com.google.android.gsf"

    /** versionName of [pkg] if it is installed, else null. */
    fun installedVersion(context: Context, pkg: String): String? = try {
        context.packageManager.getPackageInfo(pkg, 0).versionName ?: ""
    } catch (e: PackageManager.NameNotFoundException) {
        null
    }

    fun launchIntent(context: Context, pkg: String): Intent? = context.packageManager.getLaunchIntentForPackage(pkg)

    /**
     * The Google Services Framework Android ID (hex) that Google asks owners of uncertified devices to register, when a
     * Google apps package the user brought (ANAL-211) is installed. Null if GSF is missing or does not answer.
     * Not tested: no OpenBook image contains GSF.
     */
    fun gsfAndroidId(context: Context): String? = try {
        context.contentResolver.query(
            Uri.parse("content://com.google.android.gsf.gservices"), null, null, arrayOf("android_id"), null,
        )?.use { c -> if (c.moveToFirst() && c.columnCount >= 2) c.getString(1)?.toLongOrNull()?.toString(16) else null }
    } catch (e: RuntimeException) {
        Log.i(TAG, "GSF Android ID not readable: $e")
        null
    }

    /** `ro.boot.verifiedbootstate`: orange on OpenBook (AOSP test keys, or the user's own, on an unlocked device). */
    fun verifiedBootState(): String = SystemProperties.get("ro.boot.verifiedbootstate", "")
}
