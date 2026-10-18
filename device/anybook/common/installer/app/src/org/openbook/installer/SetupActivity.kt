// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Wifi
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import org.openbook.installer.ui.OpenBookMark
import org.openbook.installer.ui.OpenBookTheme
import org.openbook.installer.ui.PrimaryButton
import org.openbook.installer.ui.TextActionButton
import org.openbook.installer.ui.TonalButton

/**
 * OpenBook setup: the first screen of an installed system (docs/installer.md §3.6). AOSP has no setup wizard of its
 * own (Provision only sets the provisioned bit), so this one asks for what a laptop needs before its first use: the
 * language (pre-selected from the wizard's choice, androidboot.openbook.locale), Wi-Fi and a screen lock. There is
 * no account step. It is a home activity at a higher priority than Provision, and turns itself off when done.
 * On the live stick it steps aside at once: there the install wizard is the first screen.
 */
class SetupActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (LiveSystem.isLiveSession() || isProvisioned()) {
            finishSetup(launchHome = true)
            return
        }
        enableEdgeToEdge()
        val preset = LiveSystem.installedLocale()
        if (preset.isNotEmpty() && Locale.getDefault().toLanguageTag() != preset) LiveSystem.applyLocale(preset)
        setContent { OpenBookTheme { SetupScreens(onDone = { finishSetup(launchHome = true) }) } }
    }

    private fun isProvisioned(): Boolean =
        Settings.Global.getInt(contentResolver, Settings.Global.DEVICE_PROVISIONED, 0) != 0 &&
            Settings.Secure.getInt(contentResolver, USER_SETUP_COMPLETE, 0) != 0

    /** What Provision does, then this activity leaves the home list for good. */
    private fun finishSetup(launchHome: Boolean) {
        try {
            Settings.Global.putInt(contentResolver, Settings.Global.DEVICE_PROVISIONED, 1)
            Settings.Secure.putInt(contentResolver, USER_SETUP_COMPLETE, 1)
        } catch (e: SecurityException) {
            Log.e(TAG, "could not mark setup complete", e)
        }
        packageManager.setComponentEnabledSetting(
            ComponentName(this, SetupActivity::class.java),
            PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP,
        )
        if (launchHome) {
            startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        finish()
    }

    companion object {
        private const val TAG = "OpenBookSetup"
        private const val USER_SETUP_COMPLETE = "user_setup_complete" // Settings.Secure, @hide
    }
}

@Composable
private fun SetupScreens(onDone: () -> Unit) {
    var step by rememberSaveable { mutableIntStateOf(0) }
    // A Google apps package installed with the system (ANAL-211): its registration is the last step.
    val gapps = androidx.compose.runtime.remember { GappsInfo.installed() }
    val last = if (gapps != null) 3 else 2
    BackHandler(enabled = step > 0) { step-- }
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val cs = MaterialTheme.colorScheme
    Row(Modifier.fillMaxSize().background(cs.surface).safeDrawingPadding()) {
        // Brand panel, as on the wizard's Welcome screen.
        Box(
            Modifier.fillMaxHeight().width(420.dp).background(
                Brush.linearGradient(listOf(Color(0xFF4355B9), Color(0xFF8A5CF0), Color(0xFFE76FB8))),
            ).padding(44.dp),
        ) {
            Column(Modifier.align(Alignment.CenterStart)) {
                OpenBookMark(72.dp)
                Spacer(Modifier.height(28.dp))
                Text(stringResource(R.string.setup_brand), color = Color.White, fontSize = 52.sp,
                    lineHeight = 56.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(14.dp))
                Text(stringResource(R.string.setup_brand_sub), color = Color.White.copy(alpha = 0.9f), fontSize = 18.sp)
            }
        }
        Column(Modifier.weight(1f).fillMaxHeight().padding(horizontal = 64.dp, vertical = 48.dp)) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).widthIn(max = 880.dp)) {
                Text(stringResource(R.string.setup_overline, step + 1, last + 1), color = cs.primary, fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(10.dp))
                when (step) {
                    0 -> SetupLanguage()
                    1 -> SetupAction(
                        title = stringResource(R.string.setup_wifi_title),
                        body = stringResource(
                            if (online(ctx)) R.string.setup_wifi_connected else R.string.setup_wifi_body,
                        ),
                        icon = Icons.Rounded.Wifi,
                        action = stringResource(R.string.setup_wifi_action),
                        onAction = { ctx.startActivity(Intent(Settings.ACTION_WIFI_SETTINGS)) },
                    )
                    3 -> GappsRegistration(gapps!!)
                    else -> SetupAction(
                        title = stringResource(R.string.setup_lock_title),
                        body = stringResource(R.string.setup_lock_body),
                        icon = Icons.Rounded.Lock,
                        action = stringResource(R.string.setup_lock_action),
                        onAction = { ctx.startActivity(Intent(DevicePolicyManager.ACTION_SET_NEW_PASSWORD)) },
                    )
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End),
                verticalAlignment = Alignment.CenterVertically) {
                if (step > 0) TonalButton(stringResource(R.string.action_back), onClick = { step-- })
                if (step == last) {
                    PrimaryButton(stringResource(R.string.setup_finish), onClick = onDone,
                        icon = Icons.AutoMirrored.Rounded.ArrowForward)
                } else {
                    PrimaryButton(stringResource(R.string.action_continue), onClick = { step++ },
                        icon = Icons.AutoMirrored.Rounded.ArrowForward)
                }
            }
        }
    }
}

private fun online(ctx: android.content.Context): Boolean = try {
    val cm = ctx.getSystemService(ConnectivityManager::class.java)
    val caps = cm?.getNetworkCapabilities(cm.activeNetwork)
    caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true
} catch (e: SecurityException) {
    false
}

@Composable
private fun SetupLanguage() {
    val cs = MaterialTheme.colorScheme
    var current by rememberSaveable { mutableStateOf(Locale.getDefault().toLanguageTag()) }
    Text(stringResource(R.string.setup_title), fontSize = 40.sp, fontWeight = FontWeight.SemiBold,
        modifier = Modifier.semantics { heading() })
    Spacer(Modifier.height(10.dp))
    Text(stringResource(R.string.setup_body), fontSize = 17.sp, color = cs.onSurfaceVariant)
    Spacer(Modifier.height(24.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.Language, contentDescription = null, tint = cs.primary)
        Spacer(Modifier.width(10.dp))
        Text(stringResource(R.string.setup_language_label), fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    }
    Spacer(Modifier.height(8.dp))
    Languages.all.forEach { lang ->
        val selected = lang.locale.language == Locale.forLanguageTag(current).language &&
            (lang.locale.country.isEmpty() || lang.locale.country == Locale.forLanguageTag(current).country)
        Surface(
            onClick = {
                if (LiveSystem.applyLocale(lang.tag)) current = lang.tag
            },
            shape = RoundedCornerShape(14.dp),
            color = if (selected) cs.primaryContainer else Color.Transparent,
            modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        ) {
            Text(stringResource(lang.nativeName), fontSize = 16.sp,
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp),
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
        }
    }
}

@Composable
private fun SetupAction(title: String, body: String, icon: ImageVector, action: String, onAction: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Text(title, fontSize = 40.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.semantics { heading() })
    Spacer(Modifier.height(10.dp))
    Text(body, fontSize = 17.sp, color = cs.onSurfaceVariant)
    Spacer(Modifier.height(28.dp))
    Surface(shape = RoundedCornerShape(24.dp), color = cs.surfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(24.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = cs.primary, modifier = Modifier.size(32.dp))
            Spacer(Modifier.width(18.dp))
            Text(stringResource(R.string.setup_skip_note), fontSize = 15.sp, color = cs.onSurfaceVariant,
                modifier = Modifier.weight(1f))
            TextActionButton(action, onClick = onAction)
        }
    }
}
