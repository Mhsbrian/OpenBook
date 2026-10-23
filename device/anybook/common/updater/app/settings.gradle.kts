// OpenBook Update: the owner-visible on-laptop updater (ANAL-229). Toolchain: toolchain.sh.
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
rootProject.name = "openbook-update"
include(":app", ":systemapi-stubs")
