#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Redact device credentials and identifiers from microG test logs in place (ANAL-210), before they become evidence:
# FCM/GCM registration tokens, MCS login and check-in tokens, the check-in Android ID and serials, account cookies.
# usage: redact.sh FILE...
set -euo pipefail
for f in "$@"; do
  sed -i -E \
    -e 's/[A-Za-z0-9_-]{8,}:APA91b[A-Za-z0-9_-]+/<fcm-token>/g' \
    -e 's/APA91b[A-Za-z0-9_-]{20,}/<fcm-token>/g' \
    -e 's/((auth_token|securityToken|security_token|token|registration_id|registrationId|accountCookie)[=:] ?)[^ ,}&\]]+/\1<redacted>/g' \
    -e 's/((^|[ ,{&?])(device|user|resource|device_id|androidId|android_id|serial|meid|imei|macAddress|X-appid|appid|X-subtype)=)[^ ,}&]+/\1<redacted>/g' \
    -e 's/(Checked in as )[0-9a-f]+/\1<android-id>/g' \
    -e 's/(Refreshed token: ).*/\1<fcm-token>/g' \
    "$f"
done
