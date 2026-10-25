// OpenBook Graphics: the graphics-mode switcher's app (ANAL-246). Toolchain: ../../updater/app/toolchain.sh.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "openbook-graphics"
include(":app")
