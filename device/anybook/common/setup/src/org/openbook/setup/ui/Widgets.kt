// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.setup.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.openbook.installer.ui.Ob
import org.openbook.installer.ui.focusRing

private val RowShape = RoundedCornerShape(14.dp)

/** A radio row as in the installer's language list: label, optional secondary text on the right. */
@Composable
fun ChoiceRow(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, trailing: String? = null) {
    val cs = MaterialTheme.colorScheme
    Surface(
        color = if (selected) cs.primaryContainer else Color.Transparent,
        shape = RowShape,
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp)
            .focusRing(RowShape, gap = 1.dp)
            .clip(RowShape)
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick),
    ) {
        Row(Modifier.heightIn(min = 48.dp).padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected = selected, onClick = null)
            Spacer(Modifier.width(10.dp))
            Text(label, fontSize = 15.5.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                color = if (selected) cs.onPrimaryContainer else cs.onSurface, modifier = Modifier.weight(1f))
            if (trailing != null) {
                Text(trailing, fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(start = 12.dp))
            }
        }
    }
}

/** A setting with a switch; the whole row toggles. */
@Composable
fun SwitchRow(title: String, detail: String?, checked: Boolean, onChange: (Boolean) -> Unit, enabled: Boolean = true) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier
            .fillMaxWidth()
            .focusRing(RowShape, gap = 1.dp)
            .clip(RowShape)
            .toggleable(value = checked, enabled = enabled, role = Role.Switch, onValueChange = onChange)
            .padding(horizontal = 4.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = Ob.type.title.copy(fontSize = 16.sp), color = if (enabled) cs.onSurface else cs.onSurfaceVariant)
            if (detail != null) Text(detail, style = Ob.type.body, color = cs.onSurfaceVariant)
        }
        Spacer(Modifier.width(16.dp))
        Switch(checked = checked, onCheckedChange = null, enabled = enabled)
    }
}

/** The pill search field of the installer's language list. */
@Composable
fun SearchField(value: String, onChange: (String) -> Unit, placeholder: String, tag: String, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    TextField(
        value = value,
        onValueChange = onChange,
        singleLine = true,
        placeholder = { Text(placeholder) },
        leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
        shape = RoundedCornerShape(28.dp),
        colors = TextFieldDefaults.colors(
            focusedContainerColor = cs.surfaceContainerHigh,
            unfocusedContainerColor = cs.surfaceContainerHigh,
            focusedIndicatorColor = Color.Transparent,
            unfocusedIndicatorColor = Color.Transparent,
        ),
        modifier = modifier.fillMaxWidth().testTag(tag),
    )
}

/** A rounded card with an icon, a title and free content (Notice and Extras pages). */
@Composable
fun InfoCard(icon: ImageVector, title: String, modifier: Modifier = Modifier, iconTint: Color = MaterialTheme.colorScheme.primary,
             content: @Composable ColumnScope.() -> Unit) {
    val cs = MaterialTheme.colorScheme
    Surface(color = cs.surfaceContainerLow, shape = RoundedCornerShape(24.dp), modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(horizontal = 24.dp, vertical = 20.dp)) {
            Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(30.dp))
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(title, style = Ob.type.title, color = cs.onSurface)
                content()
            }
        }
    }
}

/** Body text in a card or under a heading. */
@Composable
fun BodyText(text: String, modifier: Modifier = Modifier) {
    Text(text, style = Ob.type.body.copy(fontSize = 15.sp, lineHeight = 22.sp), color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier)
}
