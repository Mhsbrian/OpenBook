#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Compile-checks OpenBookSetup outside Soong (no lunch, no m, no lane lock): the installer's checker with this app's
# Android.bp, manifest, res/ and src/, plus the installer's design files (Android.bp :OpenBookInstallerDesign).
# Usage: tools/compile-check.sh [--keep]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI="$HERE/../installer/app/src/org/openbook/installer/ui"
APP="$HERE" OUT="${OUT:-/tmp/ob209-setup}" EXTRA_SRCS="$UI/Art.kt $UI/Components.kt $UI/Theme.kt" \
  exec "$HERE/../installer/app/tools/compile-check.sh" "$@"
