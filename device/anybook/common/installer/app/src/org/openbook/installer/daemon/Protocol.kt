// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0

package org.openbook.installer.daemon

import org.json.JSONArray
import org.json.JSONObject

/*
 * Typed views of the messages in ../../../../../PROTOCOL.md (openbook-installd, version 1). Parsing is lenient: a
 * missing field gets a neutral default, so a newer daemon that adds fields keeps working.
 */

/** `{"ok": false, "code": ..., "error": ...}` from the daemon. */
class DaemonException(val code: String, message: String, val reply: JSONObject? = null) : Exception(message)

/** [known] is false when the daemon could not read the power supplies (then the app's own reading is used). */
data class Power(val ac: Boolean, val batteryPct: Int?, val ok: Boolean, val known: Boolean = true)

data class BootDisk(val name: String, val byId: String, val model: String, val sizeBytes: Long)

data class Source(val label: String, val fingerprint: String, val ok: Boolean, val why: String?)

/** An app add-on this image catalogues (ANAL-210), and whether the stick carries it (`on_stick`). */
data class Addon(val name: String, val title: String, val version: String, val bytes: Long, val onStick: Boolean, val why: String?)

data class JobStatus(
    val running: Boolean,
    val pct: Double,
    val step: String?,
    val steps: Map<String, String>,
    val result: InstallResult?,
)

data class Hello(
    val version: Int,
    val live: Boolean,
    val selinux: String,
    val bootDisk: BootDisk?,
    val source: Source,
    val efivars: Boolean,
    val power: Power,
    val logsOnStick: Boolean,
    val job: JobStatus?,
    val addons: List<Addon> = emptyList(),
)

data class Machine(
    val vendor: String,
    val product: String,
    val board: String,
    val firmware: String,
    val secureBoot: String,
    val ramBytes: Long,
    val cpu: String,
)

data class Component(val id: String, val state: String, val value: String, val detail: String)

data class HwInfo(val machine: Machine, val verdict: String, val components: List<Component>)

data class Partition(
    val index: Int,
    val name: String,
    val type: String,
    val fs: String,
    val label: String,
    val bytes: Long,
    val start: Long,
    val os: String,
    val encrypted: Boolean,
    val mounted: Boolean,
)

data class LayoutOption(val ok: Boolean, val why: String?, val freeBytes: Long)

data class Disk(
    val name: String,
    val byId: String,
    val model: String,
    val vendor: String,
    val serial: String,
    val sizeBytes: Long,
    val bus: String,
    val removable: Boolean,
    val readOnly: Boolean,
    val bootDisk: Boolean,
    val table: String,
    val os: List<String>,
    val freeBytes: Long,
    val largestFreeBytes: Long,
    val partitions: List<Partition>,
    val whole: LayoutOption,
    val alongside: LayoutOption,
    val warnings: List<String>,
) {
    val selectable: Boolean get() = !bootDisk && (whole.ok || alongside.ok)
    val external: Boolean get() = "external" in warnings || bus == "usb" || removable
}

/** A segment of a before/after bar: `kind` is windows, linux, efi, openbook, other or free. */
data class Segment(val kind: String, val bytes: Long, val label: String)

/** An entry of `erases` / `keeps`. */
data class PlanPart(
    val index: Int,
    val name: String,
    val fs: String,
    val label: String,
    val os: String,
    val bytes: Long,
)

data class Operation(val op: String, val text: String)

/** One app of a Google apps package the user brought (ANAL-211), as gapps_check recorded it. */
data class GappsApp(
    val dir: String,
    val packageName: String,
    val versionName: String,
    val versionCode: Long,
    val privileged: Boolean,
    val native: String,
    val signer: String?,
    val signerSha256: String?,
)

data class GappsRefusal(val path: String, val rule: String, val why: String)

/** gapps_check's answer: accepted ([ok], [sha256] names it in `plan`), or refused with the reasons per path. */
data class GappsCheck(
    val ok: Boolean,
    val sha256: String?,
    val file: String,
    val fileBytes: Long,
    val name: String?,
    val version: String?,
    val packageSha256: String?,
    val files: Int,
    val bytes: Long,
    val apps: List<GappsApp>,
    val warnings: List<String>,
    val refused: List<GappsRefusal>,
    val refusedMore: Int,
    val code: String?,
    val error: String?,
)

/** A plan's package step: what it adds, and product's new size. */
data class PlanGapps(val name: String, val file: String, val apps: Int, val files: Int, val bytes: Long, val productBytes: Long)

data class BootPlan(val entry: String, val fallbackPath: Boolean, val nvram: String, val setDefault: Boolean)

data class Plan(
    val sha256: String,
    val layout: String,
    val targetById: String,
    val targetModel: String,
    val targetSizeBytes: Long,
    val targetBus: String,
    val confirmText: String,
    val erases: List<PlanPart>,
    val keeps: List<PlanPart>,
    val before: List<Segment>,
    val after: List<Segment>,
    val bytesToWrite: Long,
    val estimatedSeconds: Int,
    val boot: BootPlan,
    val warnings: List<String>,
    val operations: List<Operation>,
    val gapps: PlanGapps? = null,
)

data class InstallResult(
    val ok: Boolean,
    val verified: Boolean,
    val failedStep: String?,
    val error: String?,
    val bootEntry: String?,
    val nvram: String?,
    /** The firmware entry the engine created (Boot####), and whether it now starts first ("first"/"unchanged"). */
    val nvramEntry: String?,
    val bootOrder: String?,
    val fallbackPath: Boolean,
    val report: String?,
    val log: String?,
    val seconds: Int,
)

/** One message of an `apply` / `attach` stream. */
sealed interface InstallEvent {
    data class Step(val step: String, val state: String) : InstallEvent

    data class Progress(val step: String, val done: Long, val total: Long, val pct: Double, val etaSeconds: Int?) :
        InstallEvent

    data class Log(val line: String) : InstallEvent

    /** The final message: [result] when `ok` is true, otherwise [code] and [error]. */
    data class Final(val ok: Boolean, val result: InstallResult?, val code: String?, val error: String?) : InstallEvent
}

// ---------------------------------------------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------------------------------------------

/** org.json's optString turns JSON null into "null"; this returns Kotlin null instead. */
internal fun JSONObject.str(name: String): String? =
    if (!has(name) || isNull(name)) null else opt(name)?.toString()

internal fun JSONObject.text(name: String): String = str(name) ?: ""

internal fun JSONObject.intOrNull(name: String): Int? =
    if (!has(name) || isNull(name)) null else (opt(name) as? Number)?.toInt() ?: str(name)?.toIntOrNull()

internal fun JSONObject.long(name: String): Long =
    if (!has(name) || isNull(name)) 0L else (opt(name) as? Number)?.toLong() ?: str(name)?.toLongOrNull() ?: 0L

internal fun JSONObject.bool(name: String): Boolean = optBoolean(name, false)

private inline fun <T> JSONArray?.mapObjects(transform: (JSONObject) -> T): List<T> {
    if (this == null) return emptyList()
    val out = ArrayList<T>(length())
    for (i in 0 until length()) optJSONObject(i)?.let { out += transform(it) }
    return out
}

private fun JSONArray?.strings(): List<String> {
    if (this == null) return emptyList()
    val out = ArrayList<String>(length())
    for (i in 0 until length()) if (!isNull(i)) out += optString(i)
    return out
}

object Parse {
    fun hello(o: JSONObject): Hello {
        val boot = o.optJSONObject("boot_disk")
        val source = o.optJSONObject("source") ?: JSONObject()
        val power = o.optJSONObject("power")
        return Hello(
            version = o.optInt("version", 0),
            live = o.bool("live"),
            selinux = o.text("selinux"),
            bootDisk = boot?.let {
                BootDisk(it.text("name"), it.text("by_id"), it.text("model"), it.long("size_bytes"))
            },
            source = Source(source.text("label"), source.text("fingerprint"), source.bool("ok"), source.str("why")),
            efivars = o.bool("efivars"),
            power = power?.let { Power(it.bool("ac"), it.intOrNull("battery_pct"), it.optBoolean("ok", true)) }
                ?: Power(ac = false, batteryPct = null, ok = true, known = false),
            logsOnStick = o.bool("logs_on_stick"),
            job = o.optJSONObject("job")?.let(::job),
            addons = o.optJSONArray("addons")?.let { a ->
                (0 until a.length()).mapNotNull { a.optJSONObject(it) }.map {
                    Addon(it.text("name"), it.text("title"), it.text("version"), it.long("bytes"), it.bool("on_stick"), it.str("why"))
                }
            } ?: emptyList(),
        )
    }

    fun job(o: JSONObject): JobStatus {
        val steps = LinkedHashMap<String, String>()
        o.optJSONObject("steps")?.let { s -> s.keys().forEach { k -> steps[k] = s.optString(k) } }
        return JobStatus(
            running = o.bool("running"),
            pct = o.optDouble("pct", 0.0).takeUnless { it.isNaN() } ?: 0.0,
            step = o.str("step"),
            steps = steps,
            result = o.optJSONObject("result")?.let(::result),
        )
    }

    fun hwinfo(o: JSONObject): HwInfo {
        val hw = o.optJSONObject("hw") ?: o
        val m = hw.optJSONObject("machine") ?: JSONObject()
        return HwInfo(
            machine = Machine(
                vendor = m.text("vendor"),
                product = m.text("product"),
                board = m.text("board"),
                firmware = m.text("firmware"),
                secureBoot = m.text("secure_boot"),
                ramBytes = m.long("ram_bytes"),
                cpu = m.text("cpu"),
            ),
            verdict = hw.text("verdict"),
            components = hw.optJSONArray("components").mapObjects {
                Component(it.text("id"), it.text("state"), it.text("value"), it.text("detail"))
            },
        )
    }

    private fun layout(o: JSONObject?): LayoutOption =
        if (o == null) LayoutOption(false, null, 0L) else LayoutOption(o.bool("ok"), o.str("why"), o.long("free_bytes"))

    fun disks(o: JSONObject): List<Disk> = o.optJSONArray("disks").mapObjects { d ->
        val layouts = d.optJSONObject("layouts")
        Disk(
            name = d.text("name"),
            byId = d.text("by_id"),
            model = d.text("model").ifBlank { d.text("name") },
            vendor = d.text("vendor"),
            serial = d.text("serial"),
            sizeBytes = d.long("size_bytes"),
            bus = d.text("bus"),
            removable = d.bool("removable"),
            readOnly = d.bool("read_only"),
            bootDisk = d.bool("boot_disk"),
            table = d.text("table"),
            os = d.optJSONArray("os").strings(),
            freeBytes = d.long("free_bytes"),
            largestFreeBytes = d.long("largest_free_bytes"),
            partitions = d.optJSONArray("partitions").mapObjects { p ->
                Partition(
                    index = p.optInt("index"),
                    name = p.text("name"),
                    type = p.text("type"),
                    fs = p.text("fs"),
                    label = p.text("label"),
                    bytes = p.long("bytes"),
                    start = p.long("start"),
                    os = p.text("os"),
                    encrypted = p.bool("encrypted"),
                    mounted = p.bool("mounted"),
                )
            },
            whole = layout(layouts?.optJSONObject("whole")),
            alongside = layout(layouts?.optJSONObject("alongside")),
            warnings = d.optJSONArray("warnings").strings(),
        )
    }

    private fun parts(a: JSONArray?): List<PlanPart> = a.mapObjects {
        PlanPart(it.optInt("index"), it.text("name"), it.text("fs"), it.text("label"), it.text("os"), it.long("bytes"))
    }

    private fun segments(a: JSONArray?): List<Segment> = a.mapObjects {
        Segment(it.text("kind"), it.long("bytes"), it.text("label"))
    }

    fun plan(o: JSONObject): Plan {
        val p = o.optJSONObject("plan") ?: o
        val target = p.optJSONObject("target") ?: JSONObject()
        val boot = p.optJSONObject("boot") ?: JSONObject()
        return Plan(
            sha256 = p.text("plan_sha256"),
            layout = p.text("layout"),
            targetById = target.text("by_id"),
            targetModel = target.text("model"),
            targetSizeBytes = target.long("size_bytes"),
            targetBus = target.text("bus"),
            confirmText = p.text("confirm_text"),
            erases = parts(p.optJSONArray("erases")),
            keeps = parts(p.optJSONArray("keeps")),
            before = segments(p.optJSONArray("before")),
            after = segments(p.optJSONArray("after")),
            bytesToWrite = p.long("bytes_to_write"),
            estimatedSeconds = p.intOrNull("estimated_seconds") ?: 0,
            boot = BootPlan(boot.text("entry"), boot.bool("fallback_path"), boot.text("nvram"), boot.bool("set_default")),
            warnings = p.optJSONArray("warnings").strings(),
            operations = p.optJSONArray("operations").mapObjects { Operation(it.text("op"), it.text("text")) },
            gapps = p.optJSONObject("gapps")?.let { g ->
                val pkg = g.optJSONObject("package") ?: JSONObject()
                PlanGapps(
                    name = pkg.text("name"),
                    file = pkg.text("file"),
                    apps = g.optJSONArray("apps")?.length() ?: 0,
                    files = g.optInt("files"),
                    bytes = g.long("bytes"),
                    productBytes = p.optJSONObject("product")?.long("bytes") ?: 0L,
                )
            },
        )
    }

    /** gapps_check's final message, accepted or refused (the refusal arrives as `ok: false` with `refused`). */
    fun gappsCheck(o: JSONObject): GappsCheck {
        val g = o.optJSONObject("gapps") ?: JSONObject()
        val pkg = g.optJSONObject("package") ?: JSONObject()
        return GappsCheck(
            ok = o.bool("ok"),
            sha256 = o.str("gapps_sha256"),
            file = pkg.text("file"),
            fileBytes = pkg.long("bytes"),
            name = pkg.str("name"),
            version = pkg.str("version"),
            packageSha256 = pkg.str("sha256"),
            files = g.optJSONArray("files")?.length() ?: 0,
            bytes = g.long("bytes"),
            apps = g.optJSONArray("apps").mapObjects {
                GappsApp(
                    dir = it.text("dir"),
                    packageName = it.text("package"),
                    versionName = it.text("version_name"),
                    versionCode = it.long("version_code"),
                    privileged = it.bool("privileged"),
                    native = it.text("native"),
                    signer = it.str("signer"),
                    signerSha256 = it.str("signer_sha256"),
                )
            },
            warnings = o.optJSONArray("warnings").strings(),
            refused = o.optJSONArray("refused").mapObjects { GappsRefusal(it.text("path"), it.text("rule"), it.text("why")) },
            refusedMore = o.optInt("refused_more", 0),
            code = o.str("code"),
            error = o.str("error"),
        )
    }

    fun result(r: JSONObject): InstallResult = InstallResult(
        ok = r.bool("ok"),
        verified = r.bool("verified"),
        failedStep = r.str("failed_step"),
        error = r.str("error"),
        bootEntry = r.str("boot_entry"),
        nvram = r.str("nvram"),
        nvramEntry = r.str("nvram_entry"),
        bootOrder = r.str("boot_order"),
        fallbackPath = r.bool("fallback_path"),
        report = r.str("report"),
        log = r.str("log"),
        seconds = r.intOrNull("seconds") ?: 0,
    )

    /** One line of an `apply` / `attach` stream, or null for an event this app does not know. */
    fun event(o: JSONObject): InstallEvent? {
        val event = o.str("event")
        if (event == null) {
            val ok = o.bool("ok")
            return InstallEvent.Final(
                ok = ok,
                result = if (ok) o.optJSONObject("result")?.let(::result) else null,
                code = o.str("code"),
                error = o.str("error"),
            )
        }
        return when (event) {
            "step" -> InstallEvent.Step(o.text("step"), o.text("state"))
            "progress" -> InstallEvent.Progress(
                step = o.text("step"),
                done = o.long("done"),
                total = o.long("total"),
                pct = o.optDouble("pct", 0.0).takeUnless { it.isNaN() } ?: 0.0,
                etaSeconds = o.intOrNull("eta_s"),
            )
            "log" -> InstallEvent.Log(o.text("line"))
            else -> null
        }
    }
}

/** The install engine's steps, in order (PROTOCOL.md, apply). */
val INSTALL_STEPS = listOf("check_source", "prepare_disk", "boot_images", "system", "boot_entry", "verify", "report")
