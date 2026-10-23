// Compile-time stand-ins for the two Android system APIs the app calls (android.os.UpdateEngine and
// UpdateEngineCallback, @SystemApi since API 24, absent from the public SDK). The app depends on this
// module compileOnly: nothing from it is packaged, and at run time the framework's own classes are used.
plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "org.openbook.update.systemapi"
    compileSdk = 37
    defaultConfig { minSdk = 36 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
