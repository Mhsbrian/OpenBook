// SPDX-License-Identifier: Apache-2.0
package org.openbook.update.ui

import android.content.Context
import android.text.format.DateUtils
import android.text.format.Formatter
import androidx.annotation.StringRes
import org.openbook.update.R
import org.openbook.update.engine.ReleaseKind
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

object Format {
    /** "2026-10-01" as a localized date ("October 1, 2026"); unchanged when it is not a date. */
    fun date(isoDate: String): String = runCatching {
        LocalDate.parse(isoDate).format(DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG))
    }.getOrDefault(isoDate)

    fun bytes(context: Context, bytes: Long): String = Formatter.formatShortFileSize(context, bytes)

    fun ago(millis: Long, now: Long = System.currentTimeMillis()): String =
        DateUtils.getRelativeTimeSpanString(millis, now, DateUtils.MINUTE_IN_MILLIS).toString()

    @StringRes
    fun kind(kind: ReleaseKind) = when (kind) {
        ReleaseKind.MONTHLY -> R.string.kind_monthly
        ReleaseKind.QUARTERLY -> R.string.kind_quarterly
        ReleaseKind.UNKNOWN -> R.string.kind_unknown
    }

    fun slot(suffix: String?) = suffix?.removePrefix("_")?.uppercase()
}
