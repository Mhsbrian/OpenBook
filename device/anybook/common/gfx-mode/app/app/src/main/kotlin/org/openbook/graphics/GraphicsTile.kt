// SPDX-License-Identifier: Apache-2.0
package org.openbook.graphics

import android.app.PendingIntent
import android.content.Intent
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import org.openbook.graphics.data.Mode
import org.openbook.graphics.data.SystemBackend
import org.openbook.graphics.ui.MainActivity
import org.openbook.graphics.ui.modeName

/** A Quick Settings tile: the current mode; a tap opens the app (switching always asks there first). */
class GraphicsTile : TileService() {
    override fun onStartListening() {
        val tile = qsTile ?: return
        Thread {
            val s = SystemBackend.read()
            tile.state = if (s?.switchable == true) Tile.STATE_ACTIVE else Tile.STATE_UNAVAILABLE
            tile.subtitle = getString(modeName(s?.mode ?: Mode.UNKNOWN))
            tile.updateTile()
        }.start()
    }

    override fun onClick() {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE)
        startActivityAndCollapse(open)
    }
}
