import java.security.MessageDigest

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// The engine (device/anybook/common/updater/openbook-updater) ships inside the APK as an asset. It
// must match its reviewed SHA-256 in pins.json, or the build stops.
val engineFile = rootProject.layout.projectDirectory.file("../openbook-updater")
val pinsFile = rootProject.layout.projectDirectory.file("../pins.json")
fun sha256(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
val engineSha256: String = sha256(providers.fileContents(engineFile).asBytes.get())

abstract class EngineAsset : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val engine: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val pins: RegularFileProperty
    @get:OutputDirectory abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        val bytes = engine.get().asFile.readBytes()
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val pinned = Regex("\"openbook-updater\"\\s*:\\s*\"([0-9a-f]{64})\"")
            .find(pins.get().asFile.readText())?.groupValues?.get(1)
        check(digest == pinned) { "openbook-updater ($digest) differs from its pin in pins.json ($pinned)" }
        val out = outputDir.get().asFile
        out.deleteRecursively()
        out.mkdirs()
        out.resolve("openbook-updater").writeBytes(bytes)
    }
}

val engineAsset = tasks.register<EngineAsset>("engineAsset") {
    engine.set(engineFile)
    pins.set(pinsFile)
    outputDir.set(layout.buildDirectory.dir("generated/engine"))
}

android {
    namespace = "org.openbook.update"
    compileSdk = 37

    defaultConfig {
        applicationId = "org.openbook.update"
        minSdk = 36
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "ENGINE_SHA256", "\"$engineSha256\"")
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
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
        animationsDisabled = true
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

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(engineAsset, EngineAsset::outputDir)
    }
}

dependencies {
    compileOnly(project(":systemapi-stubs"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.core)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.json)

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.espresso)
    androidTestImplementation(libs.androidx.work.testing)
    debugImplementation(libs.compose.ui.test.manifest)
}
