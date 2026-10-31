// SPDX-License-Identifier: Apache-2.0
// Replay HardwareState frames through the AOSP checkout's unmodified gestures library.
// No input device is opened and no events are injected. See docs/touchpad-behavior.md.
#include <cstdarg>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <json/json.h>
#include "include/gestures.h"
#include "include/prop_registry.h"

struct GesturesTimer {
    double deadline = -1;
    GesturesTimerCallback callback = nullptr;
    void* data = nullptr;
};
static double clock_now;
static GesturesTimer* active_timer;
static Json::Value output(Json::arrayValue);
extern "C" void gestures_log(int level, const char* format, ...) {
    if (level != GESTURES_LOG_ERROR) return;
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
}
static GesturesTimer* create(void*) { return active_timer = new GesturesTimer; }
static void set(void*, GesturesTimer* timer, double delay, GesturesTimerCallback cb, void* data) {
    timer->deadline = clock_now + delay;
    timer->callback = cb;
    timer->data = data;
}
static void cancel(void*, GesturesTimer* timer) { timer->deadline = -1; }
static void free_timer(void*, GesturesTimer* timer) { delete timer; active_timer = nullptr; }
static void advance(double until) {
    unsigned guard = 0;
    while (active_timer && active_timer->deadline >= 0 && active_timer->deadline < until) {
        if (++guard > 10000) throw std::runtime_error("timer failed to advance");
        clock_now = active_timer->deadline + 1e-8;
        active_timer->deadline = -1;
        double next = active_timer->callback(clock_now, active_timer->data);
        if (next >= 0) active_timer->deadline = clock_now + next;
    }
    clock_now = until;
}
static void gesture(void*, const Gesture* g) {
    Json::Value row;
    row["delivered_at"] = clock_now;
    row["start"] = g->start_time;
    row["end"] = g->end_time;
    row["type"] = static_cast<int>(g->type);
    row["description"] = g->String();
    if (g->type == kGestureTypeButtonsChange) {
        row["down"] = g->details.buttons.down;
        row["up"] = g->details.buttons.up;
    }
    output.append(row);
}
int main(int argc, char** argv) try {
    if (argc != 2) throw std::runtime_error("usage: gesture-replay frames.json");
    Json::Value input;
    std::ifstream stream(argv[1]);
    if (!stream || !(stream >> input) || !input["frames"].isArray() || input["frames"].empty())
        throw std::runtime_error("missing frames");
    GesturesTimerProvider timers{create, set, cancel, free_timer};
    GestureInterpreter interpreter(GESTURES_VERSION);
    interpreter.Initialize(GESTURES_DEVCLASS_TOUCHPAD);
    HardwareProperties hw{};
    const auto& h = input["hardware"];
    if (h["right"].asInt() != 3905 || h["bottom"].asInt() != 2382 ||
        h["res_x"].asInt() != 31 || h["res_y"].asInt() != 31 ||
        h["max_finger_cnt"].asInt() != 5 || h["max_touch_cnt"].asInt() != 5 ||
        !h["reports_pressure"].isBool() || h["reports_pressure"].asBool())
        throw std::runtime_error("only the measured pressure-less G14 04f3:3315 is supported");
    hw.right = h["right"].asFloat(); hw.bottom = h["bottom"].asFloat();
    hw.res_x = h["res_x"].asFloat(); hw.res_y = h["res_y"].asFloat();
    hw.max_finger_cnt = h["max_finger_cnt"].asUInt();
    hw.max_touch_cnt = h["max_touch_cnt"].asUInt();
    hw.is_button_pad = true;
    hw.reports_pressure = h["reports_pressure"].asBool();
    interpreter.SetHardwareProperties(hw);
    for (const auto& name : input["properties"].getMemberNames()) {
        bool found = false;
        for (auto* p : interpreter.prop_reg()->props()) {
            if (name != p->name()) continue;
            if (!p->SetValue(input["properties"][name]))
                throw std::runtime_error("invalid property: " + name);
            found = true;
        }
        if (!found) throw std::runtime_error("unknown property: " + name);
    }
    interpreter.SetTimerProvider(&timers, nullptr);
    interpreter.SetCallback(gesture, nullptr);
    for (const auto& frame : input["frames"]) {
        double time = frame["time"].asDouble();
        if (time < clock_now) throw std::runtime_error("nonmonotonic frame");
        advance(time);
        std::vector<FingerState> fingers;
        if (!frame["fingers"].isArray() || frame["fingers"].size() > 5 ||
            frame["touch_count"].asUInt() > 5)
            throw std::runtime_error("invalid G14 contacts");
        for (const auto& f : frame["fingers"]) {
            FingerState finger{};
            finger.tracking_id = f["id"].asInt();
            finger.position_x = f["x"].asFloat(); finger.position_y = f["y"].asFloat();
            finger.tool_type = f["palm"].asBool() ? FingerState::ToolType::kPalm : FingerState::ToolType::kFinger;
            fingers.push_back(finger);
        }
        HardwareState state{};
        state.timestamp = time;
        state.msc_timestamp = frame["msc"].asDouble();
        state.buttons_down = frame["buttons"].asInt();
        state.finger_cnt = fingers.size();
        state.touch_cnt = frame["touch_count"].asUInt();
        state.fingers = fingers.data();
        interpreter.PushHardwareState(&state);
    }
    advance(clock_now + 1);
    Json::StreamWriterBuilder writer;
    writer["indentation"] = "  ";
    std::cout << Json::writeString(writer, output) << '\n';
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
