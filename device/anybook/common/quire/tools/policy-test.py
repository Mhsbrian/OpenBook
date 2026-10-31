#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Run the Q6 review's dispatch regressions against production tool methods.

Android services and storage are boundary fakes; no device, network or model is
used. Set QUIRE_POLICY_SOURCE to another tools source directory for a negative
control. The complete ControlTools file and exact settings methods are compiled;
only the settings tools' visibility changes so the probe can call them.
"""
import os
from pathlib import Path
import subprocess
import tempfile

q = Path(__file__).resolve().parent.parent
aosp = Path(os.environ.get('AOSP', str(Path.home() / 'anybook/aosp/src')))
source = Path(os.environ.get('QUIRE_POLICY_SOURCE', str(q / 'app/src/dev/openbook/quire/tools')))
jdk = aosp / 'prebuilts/jdk/jdk21/linux-x86'
with tempfile.TemporaryDirectory(prefix='quire-policy-') as tmp:
    work = Path(tmp)
    control = work / 'ControlTools.kt'
    control.write_text((source / control.name).read_text())
    text = (source / 'SettingsTools.kt').read_text()
    fragment = text[text.index('    private val changeSetting ='):text.index('    private val PAGES =')]
    fragment = fragment.replace('private val changeSetting', 'val changeSetting')
    fragment = fragment.replace('private val undoChange', 'val undoChange')
    settings = work / 'SettingsTools.kt'
    settings.write_text('package dev.openbook.quire.tools\nimport android.content.Context\n'
                        'import org.json.JSONObject\nobject SettingsTools {\n' + fragment + '}\n')
    jar = work / 'policy.jar'
    subprocess.run([str(aosp / 'external/kotlinc/bin/kotlinc'), '-nowarn', '-jvm-target', '17',
                    '-include-runtime', '-d', str(jar), str(control), str(settings),
                    *map(str, sorted((q / 'tests/policy').glob('*.kt')))],
                   check=True, env={**os.environ, 'JAVA_HOME': str(jdk)})
    raise SystemExit(subprocess.run([str(jdk / 'bin/java'), '-jar', str(jar)]).returncode)
