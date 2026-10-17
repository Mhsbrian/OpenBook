/*
 * Copyright (C) 2026 The OpenBook Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * wpa_supplicant's Android "DRIVER <cmd>" hook (BOARD_WPA_SUPPLICANT_PRIVATE_LIB) for plain mac80211/cfg80211
 * Wi-Fi on a PC (MT7925, RTW89, ATH12K, iwlwifi): no vendor nl80211 commands, everything through standard nl80211.
 * The Android framework sends these through the supplicant's AIDL interface. OpenBook has no vendor Wi-Fi HAL, so
 * the regulatory country only reaches the kernel through "COUNTRY xx" (NL80211_CMD_REQ_SET_REG); without it cfg80211
 * stays on the world domain (passive scanning only on 5 and 6 GHz). The rest follows Cuttlefish's
 * lib_driver_cmd_simulated_cf: START/STOP/MACADDR/RELOAD, and success for the vendor-specific commands mac80211
 * drivers have no equivalent for (SETSUSPENDMODE, BTCOEXMODE, RXFILTER-*, ...), which the framework treats as
 * optional. docs/g14-audio-net.md.
 */

#include <stdio.h>
#include <string.h>

#include <linux/if_ether.h>

#include "includes.h"

#include "common.h"
#include "driver.h"
#include "driver_nl80211.h"
#include "linux_ioctl.h"
#include "wpa_supplicant_i.h"

int wpa_driver_nl80211_driver_cmd(void *priv, char *cmd, char *buf, size_t buf_len) {
    struct i802_bss *bss = priv;
    struct wpa_driver_nl80211_data *drv = bss->drv;
    int ret = 0;

    if (os_strncasecmp(cmd, "COUNTRY ", 8) == 0) {
        const char *cc = cmd + 8;
        if (strlen(cc) < 2 || !wpa_driver_nl80211_ops.set_country) return -1;
        ret = wpa_driver_nl80211_ops.set_country(priv, cc);
        wpa_printf(MSG_INFO, "openbook: COUNTRY %.2s -> %d", cc, ret);
        return ret < 0 ? -1 : 0;
    }
    if (os_strcasecmp(cmd, "STOP") == 0) {
        linux_set_iface_flags(drv->global->ioctl_sock, bss->ifname, 0);
        wpa_msg(drv->ctx, MSG_INFO, WPA_EVENT_DRIVER_STATE "STOPPED");
    } else if (os_strcasecmp(cmd, "START") == 0) {
        linux_set_iface_flags(drv->global->ioctl_sock, bss->ifname, 1);
        wpa_msg(drv->ctx, MSG_INFO, WPA_EVENT_DRIVER_STATE "STARTED");
    } else if (os_strcasecmp(cmd, "MACADDR") == 0) {
        u8 macaddr[ETH_ALEN] = {0};
        ret = linux_get_ifhwaddr(drv->global->ioctl_sock, bss->ifname, macaddr);
        if (!ret) ret = os_snprintf(buf, buf_len, "Macaddr = " MACSTR "\n", MAC2STR(macaddr));
    } else if (os_strcasecmp(cmd, "RELOAD") == 0) {
        wpa_msg(drv->ctx, MSG_INFO, WPA_EVENT_DRIVER_STATE "HANGED");
    } else {
        // A vendor private command: nothing to do on a mac80211 driver.
        wpa_printf(MSG_DEBUG, "openbook: driver command '%s' ignored", cmd);
        return 0;
    }
    return ret;
}

int wpa_driver_set_p2p_noa(void *priv, u8 count, int start, int duration) {
    (void)priv; (void)count; (void)start; (void)duration;
    return 0;
}

int wpa_driver_get_p2p_noa(void *priv, u8 *buf, size_t len) {
    (void)priv; (void)buf; (void)len;
    return 0;
}

int wpa_driver_set_p2p_ps(void *priv, int legacy_ps, int opp_ps, int ctwindow) {
    (void)priv; (void)legacy_ps; (void)opp_ps; (void)ctwindow;
    return -1;
}

int wpa_driver_set_ap_wps_p2p_ie(void *priv, const struct wpabuf *beacon, const struct wpabuf *proberesp,
                                 const struct wpabuf *assocresp) {
    (void)priv; (void)beacon; (void)proberesp; (void)assocresp;
    return 0;
}
