// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer

import android.content.ClipData
import android.content.ClipboardManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.openbook.installer.ui.OpenBookTheme
import org.openbook.installer.ui.PrimaryButton
import org.openbook.installer.ui.TextActionButton

/**
 * Settings › About › Google apps registration (ANAL-211): the GSF Android ID of a system the user installed with their
 * own Google apps package, and how to register it. Enabled at boot only when that package is installed (BootReceiver).
 */
class GappsRegistrationActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val installed = GappsInfo.installed()
        setContent {
            OpenBookTheme {
                Column(
                    Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface).safeDrawingPadding()
                        .padding(horizontal = 56.dp, vertical = 40.dp),
                ) {
                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).widthIn(max = 880.dp)) {
                        if (installed != null) GappsRegistration(installed) else Text(stringResource(R.string.gapps_reg_no_gsf))
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        PrimaryButton(stringResource(R.string.action_close), onClick = { finish() })
                    }
                }
            }
        }
    }
}

/** The registration page: OpenBook setup's last step, and the Settings entry above. */
@Composable
fun GappsRegistration(installed: GappsInfo.Installed) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    var attempt by remember { mutableIntStateOf(0) }
    var id by remember { mutableStateOf<String?>(null) }
    var looked by remember { mutableStateOf(false) }
    LaunchedEffect(attempt) {
        id = withContext(Dispatchers.IO) { if (installed.hasGsf) GappsInfo.gsfId(ctx) else null }
        looked = true
    }
    Text(stringResource(R.string.gapps_reg_title), fontSize = 40.sp, fontWeight = FontWeight.SemiBold,
        modifier = Modifier.semantics { heading() })
    Spacer(Modifier.height(10.dp))
    Text(stringResource(R.string.gapps_reg_body, installed.name), fontSize = 17.sp, color = cs.onSurfaceVariant)
    Spacer(Modifier.height(24.dp))
    if (!installed.hasGsf) {
        Text(stringResource(R.string.gapps_reg_no_gsf), fontSize = 16.sp)
        return
    }
    Surface(shape = RoundedCornerShape(24.dp), color = cs.surfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(24.dp)) {
            Text(stringResource(R.string.gapps_reg_id_label), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = cs.primary)
            Spacer(Modifier.height(6.dp))
            val value = id
            if (value != null) {
                SelectionContainer {
                    Text(value, fontFamily = FontFamily.Monospace, fontSize = 30.sp, fontWeight = FontWeight.SemiBold)
                }
                Text(stringResource(R.string.gapps_reg_id_hex, GappsInfo.hex(value)), fontFamily = FontFamily.Monospace,
                    fontSize = 14.sp, color = cs.onSurfaceVariant)
                Spacer(Modifier.height(8.dp))
                TextActionButton(stringResource(R.string.gapps_reg_copy), icon = Icons.Rounded.ContentCopy, onClick = {
                    ctx.getSystemService(ClipboardManager::class.java)
                        ?.setPrimaryClip(ClipData.newPlainText("GSF Android ID", value))
                })
            } else if (looked) {
                Text(stringResource(R.string.gapps_reg_no_id), fontSize = 16.sp)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextActionButton(stringResource(R.string.gapps_reg_retry), icon = Icons.Rounded.Refresh, onClick = { attempt++ })
            }
        }
    }
    Spacer(Modifier.height(20.dp))
    Text(stringResource(R.string.gapps_reg_steps), fontSize = 16.sp, lineHeight = 26.sp)
    Spacer(Modifier.height(16.dp))
    Text(stringResource(R.string.gapps_reg_note), fontSize = 14.sp, color = cs.onSurfaceVariant)
}
