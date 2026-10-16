# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# AnyBook's Cuttlefish x86_64 board: Cuttlefish's vsoc_x86_64_only plus the AnyBook vendor policy.
# Its own device directory exists only because vendor sepolicy can be added from a BoardConfig.mk alone.

include device/google/cuttlefish/vsoc_x86_64_only/BoardConfig.mk

# Cuttlefish brings and labels its own allocator, mapper and composers.
ANYBOOK_GRAPHICS_PLATFORM_HALS := false
include device/anybook/common/graphics-amd/BoardConfig.mk
