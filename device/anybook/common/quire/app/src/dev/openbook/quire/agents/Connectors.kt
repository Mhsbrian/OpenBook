// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.agents

import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.os.PowerExemptionManager
import android.os.SystemClock
import android.os.SystemProperties
import android.util.Log
import dev.openbook.quire.Quire.TAG
import dev.openbook.quire.R

/**
 * Where Quire's agents run, in the order Quire tries them (docs/quire.md §4): the laptop's own Linux environment, then
 * a computer the person paired. Each one says why it can't be used, so Quire never fails silently.
 */
object Connectors {
    /** Why a connector can't be used now, or READY. */
    enum class State {
        READY,
        /** The image has no AVF (built without it). */
        NO_AVF,
        /** AVF is there, but the hardware gives no virtualization (KVM): no SVM/VT-x, or it is off in the firmware. */
        NO_KVM,
        TERMINAL_MISSING,
        /** The person hasn't turned on the Linux environment (Developer options). */
        TERMINAL_OFF,
        /** The Linux environment is on, but its Debian image isn't installed yet. */
        NOT_INSTALLED,
        /** The Terminal app is installing the Debian image. */
        INSTALLING,
        STOPPED,
        STARTING,
        /** The Linux environment failed (detail says how), or quired didn't answer in it. */
        ERROR,
        /** No computer is paired. */
        NOT_PAIRED,
    }

    data class Status(val connector: String, val state: State, val detail: String? = null) {
        fun describe(context: Context): String {
            val text = when (state) {
                State.READY -> R.string.agents_ready
                State.NO_AVF -> R.string.agents_no_avf
                State.NO_KVM -> R.string.agents_no_kvm
                State.TERMINAL_MISSING -> R.string.agents_no_avf
                State.TERMINAL_OFF -> R.string.agents_terminal_off
                State.NOT_INSTALLED -> R.string.agents_not_installed
                State.INSTALLING -> R.string.agents_installing
                State.STOPPED -> R.string.agents_stopped
                State.STARTING -> R.string.agents_starting
                State.ERROR -> R.string.agents_error
                State.NOT_PAIRED -> R.string.agents_not_paired
            }
            return context.getString(text) + (detail?.let { " ($it)" } ?: "")
        }
    }

    /** The laptop's Linux environment: AVF's Terminal app and the quired in its Debian guest. */
    object LinuxEnvironment {
        const val NAME = "linux-environment"
        const val TERMINAL = "com.android.virtualization.terminal"
        private const val AUTHORITY = "com.android.virtualization.terminal.agentbridge"
        private val QUIRED: Uri = Uri.parse("content://$AUTHORITY/vsock/7690")

        fun status(context: Context): Status {
            val pm = context.packageManager
            if (!pm.hasSystemFeature("android.software.virtualization_framework")) return Status(NAME, State.NO_AVF)
            // Cuttlefish's launcher sets this; on a PC, init.openbook.rc does when KVM registered (openbook-pc-setup kvm).
            if (!SystemProperties.getBoolean("ro.boot.hypervisor.vm.supported", false)) return Status(NAME, State.NO_KVM)
            val enabled = try {
                val info = pm.getApplicationInfo(TERMINAL, PackageManager.MATCH_DISABLED_COMPONENTS)
                when (pm.getApplicationEnabledSetting(TERMINAL)) {
                    PackageManager.COMPONENT_ENABLED_STATE_ENABLED -> true
                    PackageManager.COMPONENT_ENABLED_STATE_DEFAULT -> info.enabled
                    else -> false
                }
            } catch (e: PackageManager.NameNotFoundException) {
                return Status(NAME, State.TERMINAL_MISSING)
            }
            if (!enabled) return Status(NAME, State.TERMINAL_OFF)
            val bundle = try {
                context.contentResolver.call(AUTHORITY, "status", null, null)
            } catch (e: Exception) {
                return Status(NAME, State.ERROR, "the Terminal app's agent bridge: ${e.message}")
            }
            val message = bundle?.getString("message")
            return when (bundle?.getString("state")) {
                "running" -> Status(NAME, State.READY)
                "starting" -> Status(NAME, State.STARTING)
                "stopped" -> Status(NAME, State.STOPPED)
                "not_installed" -> Status(NAME, State.NOT_INSTALLED)
                "installing" -> Status(NAME, State.INSTALLING)
                else -> Status(NAME, State.ERROR, message ?: "unknown state ${bundle?.getString("state")}")
            }
        }

        /**
         * Asks the Terminal app to start the Linux environment, installing it first if it isn't (ANAL-225: the person
         * never opens the Terminal app for Quire's agents). The Terminal app runs the VM in a foreground service, and
         * may start one from the background only with an exemption, which Quire grants it first (its
         * CHANGE_DEVICE_IDLE_TEMP_WHITELIST). Blocks briefly; call off the main thread.
         */
        fun start(context: Context): Status {
            try {
                context.getSystemService(PowerExemptionManager::class.java)?.addToTemporaryAllowList(TERMINAL,
                    PowerExemptionManager.REASON_OTHER, "Quire starts the Linux environment for its agents",
                    START_EXEMPTION_MS)
            } catch (e: Exception) {
                Log.w(TAG, "agents: no start exemption for the Terminal app: ${e.message}")
            }
            val bundle = try {
                context.contentResolver.call(AUTHORITY, "start", null, null)
            } catch (e: Exception) {
                return Status(NAME, State.ERROR, "the Terminal app's agent bridge: ${e.message}")
            }
            Log.i(TAG, "agents: asked the Terminal app to start the Linux environment: ${bundle?.getString("state")}")
            return status(context)
        }

        /**
         * The Linux environment running, started (or installed and started) if it is merely stopped or not installed,
         * within [timeoutMs]. Returns the last status: READY, or why not. A Linux environment that is off, or a
         * device without AVF or KVM, is not changed here. Blocks; call off the main thread.
         */
        fun ensureRunning(context: Context, timeoutMs: Long): Status {
            var s = status(context)
            if (s.state == State.STOPPED || s.state == State.NOT_INSTALLED || s.state == State.ERROR) s = start(context)
            val deadline = SystemClock.elapsedRealtime() + timeoutMs
            while (s.state == State.STARTING || s.state == State.INSTALLING) {
                if (SystemClock.elapsedRealtime() > deadline) break
                SystemClock.sleep(POLL_MS)
                s = status(context)
            }
            Log.i(TAG, "agents: the Linux environment is ${s.state}" + (s.detail?.let { " ($it)" } ?: ""))
            return s
        }

        /**
         * The person's one step (Set up, in the note): turns the Linux environment on, as Developer options' "Linux
         * development environment" switch does, then starts it, which installs it first. Blocks briefly.
         */
        fun setUp(context: Context): Status {
            try {
                context.packageManager.setApplicationEnabledSetting(TERMINAL,
                    PackageManager.COMPONENT_ENABLED_STATE_ENABLED, 0)
                Log.i(TAG, "agents: turned the Linux environment on")
            } catch (e: Exception) {
                return Status(NAME, State.ERROR, "could not turn the Linux environment on: ${e.message}")
            }
            return start(context)
        }

        private const val START_EXEMPTION_MS = 60_000L
        private const val POLL_MS = 1000L

        /** A stream to the guest's quired, relayed by the Terminal app. */
        fun connect(context: Context): ParcelFileDescriptor =
            context.contentResolver.openFileDescriptor(QUIRED, "rw")
                ?: throw java.io.FileNotFoundException("the Terminal app returned no stream")
    }

    /**
     * A computer the person paired, running `quired serve --listen`. Its design (pairing code, an encrypted and
     * mutually authenticated channel) is under review (docs/quire-pairing.md) and not built, so nothing is paired.
     */
    object PairedComputer {
        const val NAME = "paired-computer"

        fun status(@Suppress("UNUSED_PARAMETER") context: Context): Status = Status(NAME, State.NOT_PAIRED)
    }

    /** A connector's name for people. */
    fun label(context: Context, connector: String): String = context.getString(
        if (connector == PairedComputer.NAME) R.string.agents_where_paired else R.string.agents_where_linux)

    /** Every connector's status, in the order Quire tries them. */
    fun statuses(context: Context): List<Status> =
        listOf(LinuxEnvironment.status(context), PairedComputer.status(context))
}
