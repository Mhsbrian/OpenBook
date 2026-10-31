# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Board half of native-bridge.mk: arm64 is the native bridge architecture, so Soong builds the arm64 guest
# libraries (the .native_bridge variants) and the ABI list gains arm64-v8a. Cuttlefish's vsoc_x86_64_only sets
# the same values.
TARGET_NATIVE_BRIDGE_ARCH := arm64
TARGET_NATIVE_BRIDGE_ARCH_VARIANT := armv8-a
TARGET_NATIVE_BRIDGE_CPU_VARIANT := generic
TARGET_NATIVE_BRIDGE_ABI := arm64-v8a
