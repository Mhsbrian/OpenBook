// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package dev.openbook.quire.tools

import android.app.ActivityOptions
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.view.Display
import org.json.JSONObject

/** The apps on the laptop, found by the names people use for them. */
object Apps {
    data class App(val label: String, val pkg: String, val component: ComponentName)

    /** Every app with a launcher entry, by label. */
    fun launchable(c: Context): List<App> {
        val pm = c.packageManager
        val main = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return pm.queryIntentActivities(main, PackageManager.ResolveInfoFlags.of(0))
            .map { App(it.loadLabel(pm).toString(), it.activityInfo.packageName,
                ComponentName(it.activityInfo.packageName, it.activityInfo.name)) }
            .filter { it.pkg != c.packageName }
            .distinctBy { it.pkg }
            .sortedBy { it.label.lowercase() }
    }

    /** The label of [pkg], or [pkg] itself. */
    fun label(c: Context, pkg: String): String = try {
        val pm = c.packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
    } catch (e: PackageManager.NameNotFoundException) {
        pkg
    }

    private fun simple(s: String) = s.lowercase().replace(Regex("[^\\p{L}\\p{N}]+"), " ").trim()

    /**
     * The app [name] means: a package name, or a label matched exactly, then by its first words, then anywhere ("Google
     * Chrome" for "chrome"). Throws a [ToolError] naming close matches.
     */
    fun find(c: Context, name: String, among: List<App> = launchable(c)): App {
        among.firstOrNull { it.pkg == name }?.let { return it }
        val n = simple(name).removePrefix("the ").removeSuffix(" app").trim()
        val exact = among.filter { simple(it.label) == n }
        val starts = among.filter { simple(it.label).startsWith("$n ") }
        val words = among.filter { " ${simple(it.label)} ".contains(" $n ") }
        val anywhere = among.filter { simple(it.label).contains(n) || it.pkg.lowercase().contains(n.replace(" ", "")) }
        for (set in listOf(exact, starts, words, anywhere)) if (set.isNotEmpty()) return set.first()
        throw ToolError("No app called \"$name\" is installed. Installed apps include: " +
            among.take(40).joinToString(", ") { it.label } + ".")
    }

    /** Starts [intent] on the person's screen, as a new window. */
    fun start(c: Context, intent: Intent) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val options = ActivityOptions.makeBasic().setLaunchDisplayId(Display.DEFAULT_DISPLAY)
        try {
            c.startActivity(intent, options.toBundle())
        } catch (e: ActivityNotFoundException) {
            throw ToolError("No app on the laptop can open that.")
        }
    }

    /** Browsers: apps that open web pages. The person's default first. */
    fun browsers(c: Context): List<App> {
        val pm = c.packageManager
        val web = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.org")).addCategory(Intent.CATEGORY_BROWSABLE)
        val default = pm.resolveActivity(web, PackageManager.ResolveInfoFlags.of(PackageManager.MATCH_DEFAULT_ONLY.toLong()))
            ?.activityInfo?.packageName
        return pm.queryIntentActivities(web, PackageManager.ResolveInfoFlags.of(PackageManager.MATCH_ALL.toLong()))
            .map { App(it.loadLabel(pm).toString(), it.activityInfo.packageName,
                ComponentName(it.activityInfo.packageName, it.activityInfo.name)) }
            .distinctBy { it.pkg }
            .sortedBy { if (it.pkg == default) 0 else 1 }
    }
}

object AppTools {
    private val listApps = object : Tool("list_apps", Tier.OBSERVE, "read") {
        override val description = "List the apps installed on the laptop, with their package names. Use it when " +
            "you are unsure what an app is called or whether it is installed."
        override val schema = Schema.obj("query" to Schema.str("Only apps whose name contains this (optional)."))
        override fun title(c: Context, args: JSONObject) = "Looking at the apps"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val q = args.str("query")?.lowercase()
            val apps = Apps.launchable(c).filter { q == null || it.label.lowercase().contains(q) || it.pkg.contains(q) }
            if (apps.isEmpty()) return ToolResult.text("No installed app matches \"$q\".")
            return ToolResult.text(apps.joinToString("\n") { "${it.label} (${it.pkg})" })
        }
    }

    private val openApp = object : Tool("open_app", Tier.ACT, "app") {
        override val description = "Open an app on the laptop's screen, in its own window (or bring it to the front). " +
            "Give the app's name as people say it (\"Chrome\", \"Files\", \"Settings\", \"Calculator\") or its package."
        override val schema = Schema.obj("app" to Schema.str("The app's name or package name."), required = listOf("app"))
        override fun title(c: Context, args: JSONObject) = "Opening ${args.optString("app")}"
        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val app = Apps.find(c, args.req("app"))
            note.retitle("Opening ${app.label}")
            val launch = c.packageManager.getLaunchIntentForPackage(app.pkg)
                ?: Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER).setComponent(app.component)
            Apps.start(c, launch)
            return ToolResult.text("Opened ${app.label}.")
        }
    }

    private val openUrl = object : Tool("open_url", Tier.ACT, "app") {
        override val description = "Open a web page on the laptop, in the person's browser or in the browser they name " +
            "(\"Chrome\"). Turn a site's name into its address yourself: \"fox news\" is https://www.foxnews.com. " +
            "A store link (market://search?q=... or market://details?id=...) opens in the app store the person has."
        override val schema = Schema.obj(
            "url" to Schema.str("The address, e.g. https://www.foxnews.com. http and https only."),
            "app" to Schema.str("The browser to use, e.g. \"Chrome\" (optional; default: the person's browser)."),
            required = listOf("url"))
        override fun title(c: Context, args: JSONObject): String {
            val host = runCatching { normalize(args.optString("url")).host }.getOrNull() ?: args.optString("url")
            return "Opening ${host.removePrefix("www.")}" + (args.str("app")?.let { " in $it" } ?: "")
        }

        override fun run(c: Context, args: JSONObject, note: CallNote): ToolResult {
            val uri = normalize(args.req("url"))
            if (uri.scheme == "market") {
                // A store link: the person's store app (Aurora Store, F-Droid, Play) opens it, or the one they named.
                val stores = c.packageManager.queryIntentActivities(Intent(Intent.ACTION_VIEW, uri),
                    android.content.pm.PackageManager.ResolveInfoFlags.of(0)).map { it.activityInfo.packageName }.distinct()
                if (stores.isEmpty()) throw ToolError("No app store on this laptop opens store links.")
                val named = args.str("app")?.let { n -> runCatching { Apps.find(c, n).pkg }.getOrNull() }
                val pkg = named?.takeIf { it in stores } ?: stores.first()
                note.retitle("Opening the store in ${Apps.label(c, pkg)}")
                Apps.start(c, Intent(Intent.ACTION_VIEW, uri).setPackage(pkg))
                return ToolResult.text("Opened $uri in ${Apps.label(c, pkg)}.")
            }
            val browsers = Apps.browsers(c)
            val named = args.str("app")
            val browser = if (named != null) {
                try {
                    Apps.find(c, named, browsers)
                } catch (e: ToolError) {
                    val installed = runCatching { Apps.find(c, named) }.getOrNull()
                    throw ToolError(if (installed != null) "${installed.label} can't open web pages." else
                        "\"$named\" is not installed. Browsers on this laptop: " +
                            browsers.joinToString(", ") { it.label }.ifEmpty { "none" } + ".")
                }
            } else {
                browsers.firstOrNull() ?: throw ToolError("No browser is installed on this laptop.")
            }
            val host = uri.host?.removePrefix("www.") ?: uri.toString()
            note.retitle("Opening $host in ${browser.label}")
            Apps.start(c, Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE).setPackage(browser.pkg))
            return ToolResult.text("Opened $uri in ${browser.label}.")
        }
    }

    /** A web address from what the model wrote: a missing scheme becomes https; only http and https are opened. */
    fun normalize(url: String): Uri {
        val t = url.trim()
        if (t.isEmpty()) throw ToolError("Missing \"url\".")
        val u = Uri.parse(if (Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:").containsMatchIn(t)) t else "https://$t")
        if (u.scheme?.lowercase() == "market") return u
        if (u.scheme?.lowercase() !in setOf("http", "https") || u.host.isNullOrEmpty()) {
            throw ToolError("Only web addresses (http or https) and store links (market://) can be opened this way.")
        }
        return u
    }

    val all: List<Tool> = listOf(listApps, openApp, openUrl)
}
