# The framework supplies android.os.UpdateEngine* at run time (systemapi-stubs is compile-only).
-dontwarn android.os.UpdateEngine
-dontwarn android.os.UpdateEngine$*
-dontwarn android.os.UpdateEngineCallback
# The framework calls these overrides by name: keep them.
-keep class * extends android.os.UpdateEngineCallback { *; }
