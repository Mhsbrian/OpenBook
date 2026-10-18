// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup.ui

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.LockOpen
import androidx.compose.material.icons.rounded.Wifi
import androidx.compose.material.icons.rounded.WifiOff
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import org.openbook.installer.ui.ErrorNotice
import org.openbook.installer.ui.Notice
import org.openbook.installer.ui.Ob
import org.openbook.installer.ui.SectionLabel
import org.openbook.installer.ui.StatusPill
import org.openbook.installer.ui.Tone
import org.openbook.installer.ui.TonalButton
import org.openbook.setup.LockKind
import org.openbook.setup.R
import org.openbook.setup.SetupModel
import org.openbook.setup.SetupSystem

// ------------------------------------------------------------------------------------------------ Internet

enum class Link { NONE, WIFI, ETHERNET, OTHER }

private fun linkOf(caps: NetworkCapabilities?): Link = when {
    caps == null || !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) -> Link.NONE
    caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> Link.WIFI
    caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> Link.ETHERNET
    else -> Link.OTHER
}

fun currentLink(context: Context): Link {
    val cm = context.getSystemService(ConnectivityManager::class.java) ?: return Link.NONE
    return linkOf(cm.getNetworkCapabilities(cm.activeNetwork))
}

/** The default network, kept up to date while the page is shown. */
@Composable
fun rememberLink(): Link {
    val ctx = LocalContext.current
    var link by remember { mutableStateOf(currentLink(ctx)) }
    DisposableEffect(Unit) {
        val cm = ctx.getSystemService(ConnectivityManager::class.java)
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                link = linkOf(caps)
            }

            override fun onLost(network: Network) {
                link = currentLink(ctx)
            }
        }
        try {
            cm?.registerDefaultNetworkCallback(cb, ctx.mainThreadHandler)
        } catch (e: RuntimeException) {
            android.util.Log.w(SetupSystem.TAG, "no network callback", e)
        }
        onDispose { runCatching { cm?.unregisterNetworkCallback(cb) } }
    }
    return link
}

@Composable
fun linkName(link: Link): String = stringResource(
    when (link) {
        Link.WIFI -> R.string.link_wifi
        Link.ETHERNET -> R.string.link_ethernet
        Link.OTHER -> R.string.link_other
        Link.NONE -> R.string.link_none
    },
)

@Composable
fun NetworkPage(model: SetupModel) {
    val ctx = LocalContext.current
    val link = rememberLink()
    val online = link != Link.NONE
    PageFrame(model, stringResource(R.string.network_title), stringResource(R.string.network_lede)) {
        InfoCard(
            icon = if (online) Icons.Rounded.Wifi else Icons.Rounded.WifiOff,
            title = stringResource(if (online) R.string.network_online else R.string.network_offline),
            modifier = Modifier.widthIn(max = 760.dp),
        ) {
            BodyText(if (online) stringResource(R.string.network_online_body, linkName(link)) else stringResource(R.string.network_offline_body))
            Spacer(Modifier.height(8.dp))
            TonalButton(stringResource(R.string.network_choose), icon = Icons.Rounded.Wifi, onClick = {
                ctx.startActivity(Intent(Settings.ACTION_WIFI_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            })
        }
        Spacer(Modifier.height(18.dp))
        BodyText(stringResource(R.string.network_note), Modifier.widthIn(max = 760.dp))
    }
}

// ------------------------------------------------------------------------------------------------ About you

@Composable
fun AccountPage(model: SetupModel) {
    val ctx = LocalContext.current
    val secure = remember { SetupSystem.hasSecureLockScreen(ctx) }
    PageFrame(model, stringResource(R.string.account_title), stringResource(R.string.account_lede)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(48.dp)) {
            Column(Modifier.weight(1f)) {
                SectionLabel(stringResource(R.string.account_name_label))
                OutlinedTextField(
                    value = model.name,
                    onValueChange = { model.name = it.take(MAX_NAME) },
                    label = { Text(stringResource(R.string.account_name_hint)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth().testTag("name"),
                )
                Spacer(Modifier.height(8.dp))
                BodyText(stringResource(R.string.account_name_note))
            }
            Column(Modifier.weight(1f)) {
                SectionLabel(stringResource(R.string.lock_label))
                if (!secure) {
                    Notice(Icons.Rounded.LockOpen) { Text(stringResource(R.string.lock_unsupported), style = Ob.type.body) }
                    return@Column
                }
                listOf(LockKind.PIN to R.string.lock_pin, LockKind.PASSWORD to R.string.lock_password, LockKind.NONE to R.string.lock_none)
                    .forEach { (kind, label) ->
                        ChoiceRow(stringResource(label), model.lockKind == kind, onClick = {
                            model.lockKind = kind
                            model.secret = ""
                            model.secretAgain = ""
                            model.accountError = null
                        })
                    }
                Spacer(Modifier.height(10.dp))
                if (model.lockKind == LockKind.NONE) {
                    Notice(Icons.Rounded.LockOpen) { Text(stringResource(R.string.lock_none_note), style = Ob.type.body) }
                } else {
                    val pin = model.lockKind == LockKind.PIN
                    val type = if (pin) KeyboardType.NumberPassword else KeyboardType.Password
                    OutlinedTextField(
                        value = model.secret,
                        onValueChange = { model.secret = it },
                        label = { Text(stringResource(if (pin) R.string.lock_pin_hint else R.string.lock_password_hint)) },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = type, imeAction = ImeAction.Next),
                        modifier = Modifier.fillMaxWidth().testTag("secret"),
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = model.secretAgain,
                        onValueChange = { model.secretAgain = it },
                        label = { Text(stringResource(R.string.lock_again_hint)) },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = type, imeAction = ImeAction.Done),
                        modifier = Modifier.fillMaxWidth().testTag("secret-again"),
                    )
                }
                model.accountError?.let {
                    Spacer(Modifier.height(10.dp))
                    ErrorNotice(it)
                }
                if (model.lockSet != LockKind.NONE) {
                    Spacer(Modifier.height(10.dp))
                    StatusPill(stringResource(R.string.lock_set, lockName(model.lockSet)), Tone.OK, icon = Icons.Rounded.Lock)
                }
            }
        }
    }
}

@Composable
fun lockName(kind: LockKind): String = stringResource(
    when (kind) {
        LockKind.PIN -> R.string.lock_pin
        LockKind.PASSWORD -> R.string.lock_password
        LockKind.NONE -> R.string.lock_none
    },
)

private const val MAX_NAME = 64
