// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui

import androidx.annotation.DrawableRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.update.R
import org.openbook.update.data.Step

/** The large status at the top of the main screen. */
@Composable
fun StatusHero(
    @DrawableRes icon: Int?,
    container: Color,
    onContainer: Color,
    title: String,
    body: String?,
    busy: Boolean = false,
) {
    Column(Modifier.fillMaxWidth().padding(top = 24.dp, bottom = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(96.dp).clip(CircleShape).background(container), contentAlignment = Alignment.Center) {
            if (busy) CircularProgressIndicator(Modifier.size(88.dp), color = onContainer, strokeWidth = 3.dp)
            if (icon != null) Icon(painterResource(icon), contentDescription = null, tint = onContainer, modifier = Modifier.size(44.dp))
        }
        Spacer(Modifier.size(20.dp))
        Text(title, style = MaterialTheme.typography.headlineMedium, textAlign = TextAlign.Center,
             modifier = Modifier.semantics { heading() })
        if (body != null) {
            Spacer(Modifier.size(8.dp))
            Text(body, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant,
                 textAlign = TextAlign.Center)
        }
    }
}

/** A titled card of label/value rows. */
@Composable
fun DetailsCard(title: String?, rows: List<Pair<String, String>>, modifier: Modifier = Modifier, header: @Composable () -> Unit = {}) {
    OutlinedCard(modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            header()
            if (title != null) {
                Text(title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.size(8.dp))
            }
            rows.forEach { (label, value) ->
                Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                         modifier = Modifier.weight(1f))
                    Spacer(Modifier.width(16.dp))
                    Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium, textAlign = TextAlign.End)
                }
            }
        }
    }
}

/** The preparation checklist: what happened to the release so far, and what comes next. */
@Composable
fun Checklist(steps: List<Step>, modifier: Modifier = Modifier) {
    OutlinedCard(modifier.fillMaxWidth()) {
        Column(Modifier.padding(vertical = 8.dp)) {
            steps.forEach { step -> ChecklistRow(step) }
        }
    }
}

@Composable
private fun ChecklistRow(step: Step) {
    val label = stringResource(when (step.id) {
        Step.Id.DOWNLOADED -> R.string.step_downloaded
        Step.Id.VERIFIED -> R.string.step_verified
        Step.Id.CHECKED_ADAPTATIONS -> R.string.step_checked
        Step.Id.BUILT_FOR_LAPTOP -> R.string.step_built
        Step.Id.READY -> R.string.step_ready
    })
    val detail = when {
        step.status == Step.Status.NOT_YET_AVAILABLE -> stringResource(R.string.step_not_yet)
        step.status == Step.Status.FAILED -> stringResource(R.string.step_failed)
        step.id == Step.Id.CHECKED_ADAPTATIONS -> stringResource(R.string.step_checked_detail)
        else -> null
    }
    val scheme = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(24.dp), contentAlignment = Alignment.Center) {
            when (step.status) {
                Step.Status.DONE -> Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = scheme.primary)
                Step.Status.ACTIVE -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                Step.Status.PENDING -> Box(Modifier.size(16.dp).clip(CircleShape).background(scheme.outlineVariant))
                Step.Status.NOT_YET_AVAILABLE -> Icon(Icons.Filled.Lock, contentDescription = null, tint = scheme.outline,
                                                      modifier = Modifier.size(20.dp))
                Step.Status.FAILED -> Icon(Icons.Filled.Close, contentDescription = null, tint = scheme.error)
            }
        }
        Spacer(Modifier.width(16.dp))
        Column(Modifier.weight(1f)) {
            val dim = step.status == Step.Status.PENDING || step.status == Step.Status.NOT_YET_AVAILABLE
            Text(label, style = MaterialTheme.typography.bodyLarge, color = if (dim) scheme.onSurfaceVariant else scheme.onSurface)
            if (detail != null) Text(detail, style = MaterialTheme.typography.bodySmall, color = scheme.onSurfaceVariant)
        }
    }
}

/** The OpenBook mark at the foot of the update screens. */
@Composable
fun OpenBookMark(modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(vertical = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(painterResource(R.drawable.ic_book), contentDescription = null, tint = MaterialTheme.colorScheme.primary,
                 modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("OpenBook", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                 letterSpacing = 0.5.sp, color = MaterialTheme.colorScheme.onSurface)
        }
        Spacer(Modifier.size(4.dp))
        Text(stringResource(R.string.tagline), style = MaterialTheme.typography.bodySmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
    }
}
