// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup

import android.content.Context
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.android.internal.widget.LockscreenCredential
import java.util.Locale
import java.util.TimeZone

/**
 * The pages, in order (docs/setup.md). [optional] pages have a Skip button. REGISTER is only there on a system installed
 * with a Google apps package the user provided (ANAL-211).
 */
enum class Page(val optional: Boolean = false) {
    WELCOME, LANGUAGE, KEYBOARD, NETWORK(optional = true), TIME, ACCOUNT(optional = true), NOTICE,
    EXTRAS(optional = true), REGISTER, DONE
}

enum class LockKind { PIN, PASSWORD, NONE }

/**
 * Setup's state, kept in a ViewModel (SetupActivity.Holder) so it survives the activity being restarted. Each page's
 * choice is applied when the user leaves the page forward ([next]); the 24-hour and automatic-time switches apply at
 * once.
 */
class SetupModel(private val context: Context) {
    /** The user's own Google apps package, if the system was installed with one. */
    val gapps: SetupSystem.Gapps? = SetupSystem.gapps()

    /** This system's pages. */
    val pages: List<Page> = Page.entries.filter { it != Page.REGISTER || gapps != null }

    var page by mutableStateOf(Page.WELCOME)
        private set

    /** [p]'s step number, 1-based. */
    fun number(p: Page): Int = pages.indexOf(p) + 1

    // Language and region
    var language by mutableStateOf(SetupSystem.languageOf(Locale.getDefault()) ?: "en")
    var locale by mutableStateOf(Locale.getDefault())

    // Keyboard
    var layout by mutableStateOf<String?>(null)
    var layoutsApplied by mutableIntStateOf(-1)

    // Date and time
    var zoneId by mutableStateOf(TimeZone.getDefault().id)
    var zoneChosen by mutableStateOf(false)

    // About you
    var name by mutableStateOf(SetupSystem.userName(context))
    var lockKind by mutableStateOf(if (SetupSystem.hasSecureLockScreen(context)) LockKind.PIN else LockKind.NONE)
    var secret by mutableStateOf("")
    var secretAgain by mutableStateOf("")
    var accountError by mutableStateOf<String?>(null)

    /** The screen lock this setup has set, so going back can change it (setLockCredential needs the old one). */
    private var appliedLock: LockscreenCredential = LockscreenCredential.createNone()
    var lockSet by mutableStateOf(LockKind.NONE)
        private set

    fun back() {
        val i = pages.indexOf(page)
        if (i > 0) page = pages[i - 1]
    }

    /** Applies the current page and moves on; stays (and sets an error) when the page's input is not valid. */
    fun next(skip: Boolean = false) {
        if (!skip && !apply(page)) return
        if (page != Page.DONE) page = pages[pages.indexOf(page) + 1]
    }

    private fun apply(p: Page): Boolean = when (p) {
        Page.LANGUAGE -> {
            if (locale != Locale.getDefault()) SetupSystem.applyLocale(locale)
            true
        }
        Page.KEYBOARD -> {
            layout?.let { layoutsApplied = SetupSystem.applyKeyboardLayout(context, it) }
            true
        }
        Page.TIME -> {
            if (zoneChosen && zoneId != TimeZone.getDefault().id) SetupSystem.setTimeZone(context, zoneId)
            true
        }
        Page.ACCOUNT -> applyAccount()
        else -> true
    }

    private fun applyAccount(): Boolean {
        accountError = null
        val n = name.trim()
        if (n.isNotEmpty() && n != SetupSystem.userName(context)) SetupSystem.setUserName(context, n)
        val wanted = when (lockKind) {
            LockKind.NONE -> LockscreenCredential.createNone()
            LockKind.PIN -> {
                if (secret.length < MIN_SECRET || !secret.all { it.isDigit() }) return fail(R.string.lock_error_pin)
                LockscreenCredential.createPin(secret)
            }
            LockKind.PASSWORD -> {
                if (secret.length < MIN_SECRET) return fail(R.string.lock_error_password)
                LockscreenCredential.createPassword(secret)
            }
        }
        if (lockKind != LockKind.NONE && secret != secretAgain) return fail(R.string.lock_error_mismatch)
        if (wanted.isNone && appliedLock.isNone) return true
        if (!SetupSystem.setScreenLock(context, wanted, appliedLock)) return fail(R.string.lock_error_failed)
        appliedLock = wanted
        lockSet = lockKind
        secret = ""
        secretAgain = ""
        Log.i(SetupSystem.TAG, "screen lock: ${lockKind.name.lowercase()}")
        return true
    }

    private fun fail(msg: Int): Boolean {
        accountError = context.getString(msg)
        return false
    }

    companion object {
        /** LockPatternUtils.MIN_LOCK_PASSWORD_SIZE. */
        const val MIN_SECRET = 4
    }
}
