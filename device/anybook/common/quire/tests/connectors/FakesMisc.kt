// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package android.content.pm

class PackageManager {
    class NameNotFoundException : Exception()
    class ApplicationInfo(val enabled: Boolean)
    /** False: the Linux environment is off (Developer options' switch). */
    var terminalEnabled = true
    fun hasSystemFeature(name: String) = true
    fun getApplicationInfo(pkg: String, flags: Int) = ApplicationInfo(terminalEnabled)
    fun getApplicationEnabledSetting(pkg: String) =
        if (terminalEnabled) COMPONENT_ENABLED_STATE_ENABLED else COMPONENT_ENABLED_STATE_DISABLED
    fun setApplicationEnabledSetting(pkg: String, state: Int, flags: Int) {
        terminalEnabled = state == COMPONENT_ENABLED_STATE_ENABLED
    }
    companion object {
        const val MATCH_DISABLED_COMPONENTS = 0x200
        const val COMPONENT_ENABLED_STATE_DEFAULT = 0
        const val COMPONENT_ENABLED_STATE_ENABLED = 1
        const val COMPONENT_ENABLED_STATE_DISABLED = 2
    }
}
