plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "org.openbook.graphics"
    compileSdk = 37

    defaultConfig {
        applicationId = "org.openbook.graphics"
        minSdk = 36
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Unsigned: build.sh signs it on the host with the OpenBook app key (never in Gradle).
            signingConfig = null
            // No VCS stamp: the bytes depend on the sources only (build.sh records the commit).
            vcsInfo.include = false
        }
    }
    buildFeatures {
        compose = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
    // Reproducible output: no Play dependency block, no VCS stamp (provenance is recorded by build.sh).
    dependenciesInfo {
        includeInApk = false
        includeInBundle = false
    }
    packaging {
        resources.excludes += setOf("META-INF/*.version", "META-INF/**/LICENSE*", "DebugProbesKt.bin", "kotlin-tooling-metadata.json")
    }
    lint {
        abortOnError = true
        checkReleaseBuilds = true
        warningsAsErrors = false
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.core)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
}
