// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Celebration
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.ui.Ob
import org.openbook.installer.ui.OpenBookMark
import org.openbook.installer.ui.PrimaryButton
import org.openbook.installer.ui.TextActionButton
import org.openbook.installer.ui.TonalButton
import org.openbook.setup.Page
import org.openbook.setup.R
import org.openbook.setup.SetupModel

/** The window is 1920 x 1080 dp in Cuttlefish and 1920 x 1200 dp on the G14 (density 240); smaller ones are compact. */
val LocalCompact = staticCompositionLocalOf { false }

@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun SetupApp(model: SetupModel, onSkipAll: () -> Unit, onDone: () -> Unit) {
    // Always taken: Back on the first page would finish the home activity, and the system would only start it again.
    BackHandler { model.back() }
    // Test tags become resource ids, so scripts/setup/setup-walk.sh can find the text fields.
    BoxWithConstraints(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface).safeDrawingPadding()
            .semantics { testTagsAsResourceId = true },
    ) {
        CompositionLocalProvider(LocalCompact provides (maxWidth < 1040.dp || maxHeight < 680.dp)) {
            when (model.page) {
                Page.WELCOME -> WelcomePage(model, onSkipAll)
                else -> Row(Modifier.fillMaxSize()) {
                    StepRail(model, Modifier.width(if (LocalCompact.current) 236.dp else 286.dp).fillMaxHeight())
                    Box(Modifier.weight(1f).fillMaxHeight()) {
                        when (model.page) {
                            Page.LANGUAGE -> LanguagePage(model)
                            Page.KEYBOARD -> KeyboardPage(model)
                            Page.NETWORK -> NetworkPage(model)
                            Page.TIME -> TimePage(model)
                            Page.ACCOUNT -> AccountPage(model)
                            Page.NOTICE -> NoticePage(model)
                            Page.EXTRAS -> ExtrasPage(model)
                            Page.REGISTER -> RegisterPage(model)
                            else -> DonePage(model, onDone)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun pageLabel(page: Page): String = stringResource(
    when (page) {
        Page.WELCOME -> R.string.rail_welcome
        Page.LANGUAGE -> R.string.rail_language
        Page.KEYBOARD -> R.string.rail_keyboard
        Page.NETWORK -> R.string.rail_network
        Page.TIME -> R.string.rail_time
        Page.ACCOUNT -> R.string.rail_account
        Page.NOTICE -> R.string.rail_notice
        Page.EXTRAS -> R.string.rail_extras
        Page.REGISTER -> R.string.rail_register
        Page.DONE -> R.string.rail_done
    },
)

/**
 * A page of steps 2-9: overline, headline and lede, the content, and the action row (Back on the left; Skip on optional
 * pages and Continue on the right), which always stays visible. [scroll]: the content scrolls as a whole; pages with
 * their own lists pass false and get the remaining height.
 */
@Composable
fun PageFrame(
    model: SetupModel,
    title: String,
    lede: String?,
    scroll: Boolean = true,
    primary: @Composable RowScope.() -> Unit = {
        PrimaryButton(stringResource(R.string.action_continue), onClick = { model.next() },
            icon = Icons.AutoMirrored.Rounded.ArrowForward)
    },
    content: @Composable ColumnScope.() -> Unit,
) {
    val compact = LocalCompact.current
    val hPad: Dp = if (compact) 32.dp else 56.dp
    Column(Modifier.fillMaxSize().padding(start = hPad, end = hPad, top = if (compact) 28.dp else 40.dp, bottom = 24.dp)) {
        val page = model.page
        Text(
            stringResource(R.string.overline, model.number(page), model.pages.size, pageLabel(page)).uppercase(),
            style = Ob.type.overline,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(bottom = 10.dp),
        )
        Text(
            title,
            style = if (compact) Ob.type.headline.copy(fontSize = 32.sp, lineHeight = 40.sp) else Ob.type.headline,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.padding(bottom = 10.dp).semantics { heading() },
        )
        if (lede != null) {
            Text(lede, style = Ob.type.lede, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.widthIn(max = 760.dp).padding(bottom = 22.dp))
        }
        val body = Modifier.weight(1f).fillMaxWidth()
        Column(if (scroll) body.verticalScroll(rememberScrollState()) else body) {
            Column(Modifier.widthIn(max = 1180.dp).then(if (scroll) Modifier else Modifier.weight(1f)), content = content)
        }
        Row(Modifier.fillMaxWidth().padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically) {
            TonalButton(stringResource(R.string.action_back), onClick = { model.back() })
            Spacer(Modifier.weight(1f))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                if (page.optional) TextActionButton(stringResource(R.string.action_skip), onClick = { model.next(skip = true) })
                primary()
            }
        }
    }
}

@Composable
private fun StepRail(model: SetupModel, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    val border = cs.outlineVariant.copy(alpha = 0.45f)
    Column(
        modifier
            .background(cs.surfaceContainerLow)
            .drawBehind {
                drawLine(border, Offset(size.width - 0.5f, 0f), Offset(size.width - 0.5f, size.height), 1.dp.toPx())
            }
            .padding(start = 22.dp, end = 22.dp, top = 26.dp, bottom = 22.dp),
    ) {
        Row(Modifier.padding(start = 4.dp, bottom = 26.dp), verticalAlignment = Alignment.CenterVertically) {
            OpenBookMark(38.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.semantics(mergeDescendants = true) {}) {
                Text(stringResource(R.string.brand_name), fontSize = 23.sp, fontWeight = FontWeight.SemiBold,
                    letterSpacing = (-0.4).sp, color = cs.onSurface)
                Text(stringResource(R.string.brand_setup), fontSize = 12.5.sp, fontWeight = FontWeight.Medium,
                    color = cs.onSurfaceVariant)
            }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            model.pages.forEach { RailStep(it, model) }
        }
        Spacer(Modifier.height(16.dp))
        Surface(color = cs.surfaceContainerHigh, contentColor = cs.onSurfaceVariant, shape = RoundedCornerShape(18.dp)) {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
                Icon(Icons.Rounded.Tune, contentDescription = null, tint = cs.primary, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(12.dp))
                Text(stringResource(R.string.rail_note), fontSize = 13.sp, lineHeight = 18.sp)
            }
        }
    }
}

@Composable
private fun RailStep(step: Page, model: SetupModel) {
    val cs = MaterialTheme.colorScheme
    val current = model.page
    val number = model.number(step)
    val done = number < model.number(current)
    val now = step == current
    val connectorColor = if (number <= model.number(current)) cs.primary else cs.outlineVariant
    val label = pageLabel(step)
    val state = stringResource(
        when {
            now -> R.string.rail_state_current
            done -> R.string.rail_state_done
            else -> R.string.rail_state_upcoming
        },
    )
    val description = stringResource(R.string.rail_step_description, number, model.pages.size, label, state)
    Row(
        Modifier
            .fillMaxWidth()
            .drawWithContent {
                drawContent()
                if (number > 1) {
                    val x = 20.dp.toPx()
                    drawLine(connectorColor, Offset(x, -7.dp.toPx()), Offset(x, 7.dp.toPx()), 2.dp.toPx())
                }
            }
            .clip(RoundedCornerShape(16.dp))
            .background(if (now) cs.primaryContainer.copy(alpha = 0.7f) else Color.Transparent)
            .padding(horizontal = 4.dp, vertical = 7.dp)
            .clearAndSetSemantics { contentDescription = description },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(34.dp), contentAlignment = Alignment.Center) {
            val dot = when {
                now -> Modifier
                    .drawBehind { drawCircle(cs.primary.copy(alpha = 0.18f), radius = size.minDimension / 2f + 5.dp.toPx()) }
                    .background(cs.primary, CircleShape)
                done -> Modifier.background(cs.primary, CircleShape)
                else -> Modifier.background(cs.surfaceContainerLow, CircleShape).border(2.dp, cs.outlineVariant, CircleShape)
            }
            Box(Modifier.size(30.dp).then(dot), contentAlignment = Alignment.Center) {
                when {
                    now && step == Page.DONE -> Icon(Icons.Rounded.Celebration, null, tint = cs.onPrimary, modifier = Modifier.size(18.dp))
                    done -> Icon(Icons.Rounded.Check, null, tint = cs.onPrimary, modifier = Modifier.size(18.dp))
                    else -> Text(number.toString(), fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold,
                        color = if (now) cs.onPrimary else cs.onSurfaceVariant)
                }
            }
        }
        Spacer(Modifier.width(14.dp))
        Text(label, fontSize = 15.sp, fontWeight = if (done || now) FontWeight.SemiBold else FontWeight.Medium,
            color = if (done || now) cs.onSurface else cs.onSurfaceVariant)
    }
}
