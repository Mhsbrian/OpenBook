# SPDX-License-Identifier: Apache-2.0
# OpenBook ARM-translation corpus (ANAL-380): an unattended, fixed benchmark run of Godot's TPS demo. Added by
# scripts/perf/workloads/build-tps-demo.sh as an autoload; not part of the upstream demo.
#
# Skips the menu, loads the level (player and robots spawn as in a normal game), then flies its own camera through
# the level's player and robot spawn points in a fixed order and at a fixed speed. After WARMUP_S it records every
# frame that completes inside a MEASURE_S window, prints one OPENBOOK_BENCH result line (frame-time percentiles, the
# window actually covered, the frame that crossed its end, and the average of Godot's TIME_PROCESS monitor) to the
# log, and quits. No input is needed or read. vsync is off and the frame rate uncapped, so the result shows what the
# CPU and GPU can do. Time is wall-clock time, not the engine's delta (which the engine clamps on slow frames): every
# run follows the same camera path at the same speed, however fast it renders.
#
# Every OPENBOOK_BENCH line carries pid=: the runner accepts only the lines of the process its own launch started.
extends Node

const LEVEL := "res://level/level.tscn"
const WARMUP_S := 10.0
const MEASURE_S := 60.0
const SPEED := 6.0  # metres per second along the path
const EYE := Vector3(0, 2.5, 0)

var cam: Camera3D
var points: Array[Vector3] = []
var lengths := PackedFloat64Array()
var path_length := 0.0
var level_us := -1
var frame_ms := PackedFloat64Array()
var process_ms := 0.0
var last_us := 0
var window_us := -1
var crossing_ms := 0.0
var done := false
var pid := OS.get_process_id()


func _ready() -> void:
	Settings.config_file.set_value("video", "vsync", DisplayServer.VSYNC_DISABLED)
	Settings.config_file.set_value("video", "max_fps", 0)
	print("OPENBOOK_BENCH start pid=%d arch=%s renderer=%s driver=%s adapter=%s" % [pid, Engine.get_architecture_name(),
		ProjectSettings.get_setting("rendering/renderer/rendering_method.mobile"),
		RenderingServer.get_current_rendering_driver_name(), RenderingServer.get_video_adapter_name()])
	_load_level.call_deferred()


func _load_level() -> void:
	var main := get_tree().current_scene
	main.change_scene_to_packed(load(LEVEL))
	await get_tree().process_frame
	var level := main.get_child(0)
	for group in ["PlayerSpawnpoints", "RobotSpawnpoints"]:
		var node := level.get_node_or_null(group)
		if node:
			for c in node.get_children():
				if c is Node3D:
					points.append((c as Node3D).global_position + EYE)
	if points.size() < 2:
		print("OPENBOOK_BENCH error pid=%d no path (%d points)" % [pid, points.size()])
		get_tree().quit(2)
		return
	points.append(points[0])
	for i in points.size() - 1:
		lengths.append(points[i].distance_to(points[i + 1]))
		path_length += lengths[i]
	cam = Camera3D.new()
	cam.far = 500.0
	level.add_child(cam)
	cam.global_position = points[0]
	cam.make_current()
	level_us = Time.get_ticks_usec()
	print("OPENBOOK_BENCH level loaded pid=%d points=%d path_m=%.0f" % [pid, points.size(), path_length])


func _process(_delta: float) -> void:
	if level_us < 0 or done:
		return
	var now := Time.get_ticks_usec()
	var since_level := (now - level_us) / 1e6
	_fly(since_level)
	if not cam.current:
		cam.make_current()  # the player's camera takes over when it spawns
	if since_level >= WARMUP_S:
		if window_us < 0:
			window_us = now  # the window opens at a frame boundary: no frame straddles its start
		elif now - window_us <= MEASURE_S * 1e6:
			frame_ms.append((now - last_us) / 1000.0)
			process_ms += Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
		else:
			crossing_ms = (now - last_us) / 1000.0  # the frame that crossed the end: reported, not counted
			_report()
	last_us = now


func _fly(t: float) -> void:
	var d := fmod(t * SPEED, path_length)
	var i := 0
	while i < lengths.size() - 1 and d > lengths[i]:
		d -= lengths[i]
		i += 1
	var a := points[i]
	var b := points[i + 1]
	cam.global_position = a.lerp(b, clampf(d / maxf(lengths[i], 0.01), 0.0, 1.0))
	if cam.global_position.distance_to(b) > 0.1:
		cam.look_at(b, Vector3.UP)


func _report() -> void:
	done = true
	var s := frame_ms.duplicate()
	s.sort()
	var n := s.size()
	var total := 0.0
	for v in s:
		total += v
	var pct := func(p: float) -> float: return s[clampi(int(ceil(p * n)) - 1, 0, n - 1)]
	# window_s: from the window's opening to the end of its last counted frame (at most MEASURE_S).
	# engine_process_ms_avg: Godot's TIME_PROCESS monitor (the engine's frame-processing time), not CPU time.
	print("OPENBOOK_BENCH result pid=%d frames=%d window_s=%.3f fps_avg=%.2f p50_ms=%.3f p95_ms=%.3f p99_ms=%.3f max_ms=%.3f crossing_frame_ms=%.3f engine_process_ms_avg=%.3f arch=%s size=%s" % [
		pid, n, total / 1000.0, n / (total / 1000.0), pct.call(0.5), pct.call(0.95), pct.call(0.99), s[n - 1],
		crossing_ms, process_ms / n, Engine.get_architecture_name(), get_viewport().get_visible_rect().size])
	await get_tree().create_timer(1.0).timeout
	get_tree().quit(0)
