// SPDX-License-Identifier: Apache-2.0
package com.android.server.am;

import android.content.pm.ApplicationInfo;
import android.content.pm.ServiceInfo;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.function.Consumer;

/** Runs against the image's actual services.jar via app_process in the disposable VM. */
public final class PolicyProbe {
    private static int checks;
    private static Method compatible;
    private static ServiceInfo source, target;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        checks++;
        System.out.println("PASS " + name);
    }

    private static ServiceInfo copy(ServiceInfo info) {
        ServiceInfo result = new ServiceInfo(info);
        result.applicationInfo = new ApplicationInfo(info.applicationInfo);
        return result;
    }

    private static boolean accepts(ServiceInfo from, ServiceInfo to) throws Exception {
        return (Boolean) compatible.invoke(null, from, to);
    }

    private static void reject(String name, Consumer<ServiceInfo> mutation) throws Exception {
        ServiceInfo changed = copy(target);
        mutation.accept(changed);
        check(name, !accepts(source, changed));
    }

    public static void main(String[] ignored) throws Exception {
        Class<?> policy = Class.forName("com.android.server.am.NativeBridgeServiceFallback");
        compatible = policy.getDeclaredMethod("compatible", ServiceInfo.class, ServiceInfo.class);
        compatible.setAccessible(true);
        source = new ServiceInfo();
        source.name = "org.chromium.content.app.NativeOnlySandboxedProcessService0";
        source.packageName = "dev.openbook.policy";
        source.processName = "dev.openbook.policy:renderer";
        source.permission = "dev.openbook.policy.SIGNATURE";
        source.flags = ServiceInfo.FLAG_NATIVE_SERVICE | ServiceInfo.FLAG_ISOLATED_PROCESS
                | ServiceInfo.FLAG_USE_APP_ZYGOTE;
        source.enabled = true;
        source.applicationInfo = new ApplicationInfo();
        source.applicationInfo.packageName = source.packageName;
        source.applicationInfo.uid = 10123;
        source.applicationInfo.enabled = true;
        target = copy(source);
        target.name = "org.chromium.content.app.SandboxedProcessService0";
        target.flags &= ~ServiceInfo.FLAG_NATIVE_SERVICE;
        check("matching declared contract", accepts(source, target));
        check("missing source", !accepts(null, target));
        check("missing target", !accepts(source, null));
        reject("cross-package service", x -> x.packageName = "another.app");
        reject("cross-package application", x -> x.applicationInfo.packageName = "another.app");
        reject("different UID", x -> x.applicationInfo.uid++);
        reject("different process", x -> x.processName += "2");
        reject("dropped permission", x -> x.permission = null);
        reject("different permission", x -> x.permission = "another.PERMISSION");
        reject("different export", x -> x.exported = true);
        reject("different direct-boot visibility", x -> x.directBootAware = true);
        reject("disabled service", x -> x.enabled = false);
        reject("disabled application", x -> x.applicationInfo.enabled = false);
        reject("missing isolation", x -> x.flags &= ~ServiceInfo.FLAG_ISOLATED_PROCESS);
        reject("different zygote policy", x -> x.flags &= ~ServiceInfo.FLAG_USE_APP_ZYGOTE);
        reject("native-only target", x -> x.flags |= ServiceInfo.FLAG_NATIVE_SERVICE);
        reject("different external-service policy", x -> x.flags |= ServiceInfo.FLAG_EXTERNAL_SERVICE);
        reject("wrong fallback component", x -> x.name += "Untrusted");
        ServiceInfo changed = copy(source);
        changed.name = "another.NativeOnlyService";
        check("unknown source component", !accepts(changed, target));
        changed = copy(target);
        ApplicationInfo.class.getDeclaredField("primaryCpuAbi").set(changed.applicationInfo, "x86_64");
        check("different ABI", !accepts(source, changed));
        Class<?> nativeZygote = Class.forName("android.os.NativeZygoteProcess");
        Method abi = nativeZygote.getMethod("isAbiSupported", String.class);
        check("native x86_64 eligible", (Boolean) abi.invoke(null, "x86_64"));
        check("ARM64 rejected", !(Boolean) abi.invoke(null, "arm64-v8a"));
        check("ARMv7 rejected", !(Boolean) abi.invoke(null, "armeabi-v7a"));
        check("secondary x86 rejected", !(Boolean) abi.invoke(null, "x86"));
        check("null ABI uses native default", (Boolean) abi.invoke(null, new Object[] {null}));
        Object process = nativeZygote.getConstructor().newInstance();
        for (Method method : nativeZygote.getMethods()) {
            if (!method.getName().equals("start") && !method.getName().equals("startChildZygote")) continue;
            Class<?>[] types = method.getParameterTypes();
            Object[] args = new Object[types.length];
            for (int i = 0; i < args.length; i++) {
                if (types[i] == int.class) args[i] = 0;
                else if (types[i] == long.class) args[i] = 0L;
                else if (types[i] == boolean.class) args[i] = false;
            }
            args[method.getName().equals("start") ? 9 : 7] = "arm64-v8a";
            boolean rejected = false;
            long start = System.nanoTime();
            try {
                method.invoke(process, args);
            } catch (InvocationTargetException e) {
                rejected = e.getCause() instanceof IllegalArgumentException;
            }
            check(method.getName() + " rejects before connecting/using null app data",
                    rejected && System.nanoTime() - start < 1_000_000_000L);
        }
        System.out.println("POLICY_PASS checks=" + checks);
    }
}
