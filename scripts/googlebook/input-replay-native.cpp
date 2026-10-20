// SPDX-License-Identifier: Apache-2.0
// Synthetic six-second drag through the RETAINED library's public gestures API.
// No evdev, binder, keyboard, display or user-data access. Android/NDK build.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include "include/gestures.h"

struct GesturesTimer { double due = -1; GesturesTimerCallback cb; void *data; };
struct GesturesProp {};
static GesturesTimer *timer;
static double now, down_at, up_at;
static unsigned downs, ups;
static GesturesTimer *create(void*) { return timer = new GesturesTimer; }
static void set(void*, GesturesTimer *t, double delay, GesturesTimerCallback cb, void *data) {
    t->due = now + delay; t->cb = cb; t->data = data;
}
static void cancel(void*, GesturesTimer *t) { t->due = -1; }
static void destroy(void*, GesturesTimer *t) { delete t; timer = nullptr; }
static void advance(double end) {
    unsigned guard = 0;
    while (timer && timer->due >= 0 && timer->due < end) {
        if (++guard > 10000) { fprintf(stderr,"timer stalled\n"); exit(2); }
        now = timer->due + 1e-8; timer->due = -1;
        double next = timer->cb(now, timer->data);
        if (next >= 0) timer->due = now + next;
    }
    now = end;
}
static void event(void*, const Gesture *g) {
    if (g->type != kGestureTypeButtonsChange) return;
    if (g->details.buttons.down) { ++downs; down_at = now; }
    if (g->details.buttons.up) { ++ups; up_at = now; }
}
template<class T> static GesturesProp *prop(void*, const char*, T *loc, size_t n, const T *init) {
    memcpy(loc, init, n * sizeof(T)); return new GesturesProp;
}
static GesturesProp *boolean(void *v, const char *name, GesturesPropBool *loc,
                            size_t n, const GesturesPropBool *init) {
    auto *p = prop(v,name,loc,n,init);
    if (!strcmp(name,"Tap Enable") || !strcmp(name,"Tap Drag Enable")) *loc = 1;
    if (!strcmp(name,"Tap Drag Lock Enable")) *loc = 0;
    return p;
}
static GesturesProp *string_prop(void*, const char*, const char **loc, const char *const init) {
    *loc=init; return new GesturesProp;
}
static void handlers(void*,GesturesProp*,void*,GesturesPropGetHandler,GesturesPropSetHandler) {}
static void free_prop(void*,GesturesProp *p) { delete p; }
template<class T> static T symbol(void *lib, const char *name) {
    void *p = dlsym(lib,name);
    if (!p) { fprintf(stderr,"%s: %s\n",name,dlerror()); exit(2); }
    return reinterpret_cast<T>(p);
}
int main(int argc, char **argv) {
    if (argc != 3 || (strcmp(argv[2],"reset") && strcmp(argv[2],"preserve"))) return 2;
    void *lib = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!lib) { fprintf(stderr,"%s\n",dlerror()); return 2; }
#define API(n) auto n##_fn = symbol<decltype(&n)>(lib,#n)
    API(NewGestureInterpreterImpl); API(DeleteGestureInterpreter);
    API(GestureInterpreterSetHardwareProperties); API(GestureInterpreterSetCallback);
    API(GestureInterpreterSetTimerProvider); API(GestureInterpreterSetPropProvider);
    API(GestureInterpreterInitialize); API(GestureInterpreterPushHardwareState);
    GesturesTimerProvider timers{create,set,cancel,destroy};
    GesturesPropProvider props{prop<int>,nullptr,boolean,string_prop,prop<double>,handlers,free_prop};
    HardwareProperties hw{};
    hw.right=3905; hw.bottom=2382; hw.res_x=hw.res_y=31;
    hw.max_finger_cnt=hw.max_touch_cnt=5; hw.is_button_pad=1; hw.reports_pressure=false;
    bool passed=true;
    // Exact-build ABI probe of the real converter, with no contacts. Layout
    // offsets are restricted to the two SHA-pinned binaries in the runner.
    // Empty accumulators need no InputDeviceContext; MSC and SYN never consult
    // its virtual interface. No constructor for a live input device is called.
    {
        alignas(16) unsigned char accumulator[128]{}, converter[128]{}, output[128]{};
        using Ctor=void(*)(void*);
        using Process=void(*)(void*,void*,const void*); // SysV class return in RDI
        auto ctor=symbol<Ctor>(lib,"_ZN7android27MultiTouchMotionAccumulatorC1Ev");
        auto process=symbol<Process>(lib,"_ZN7android22HardwareStateConverter15processRawEventERKNS_8RawEventE");
        ctor(accumulator);
        void *ptr=accumulator; memcpy(converter+0x18,&ptr,sizeof(ptr));
        struct Raw { int64_t when,read; int32_t device,type,code,value; };
        Raw raw{1000000000,1000000000,0,4,5,1234500};
        process(output,converter,&raw);
        raw.type=raw.code=raw.value=0;
        process(output,converter,&raw);
        double first=reinterpret_cast<HardwareState*>(output)->msc_timestamp;
        raw.when+=2000000;
        process(output,converter,&raw); // timestamp-less second SYN
        double second=reinterpret_cast<HardwareState*>(output)->msc_timestamp;
        raw.type=4; raw.code=5; raw.value=0;
        process(output,converter,&raw);
        raw.type=raw.code=0;
        process(output,converter,&raw);
        double explicit_zero=reinterpret_cast<HardwareState*>(output)->msc_timestamp;
        bool ok=fabs(first-1.2345)<1e-8 && explicit_zero==0 &&
            fabs(second-(!strcmp(argv[2],"preserve")?1.2345:0))<1e-8;
        printf("INPUT_CONVERTER expected=%s first=%.6f second=%.6f explicit_zero=%.6f pass=%d\n",
               argv[2],first,second,explicit_zero,ok);
        passed &= ok;
    }
    for (int policy=0; policy<3; ++policy) {
        now=down_at=up_at=0; downs=ups=0;
        auto *g=NewGestureInterpreterImpl_fn(GESTURES_VERSION);
        if (!g) return 2;
        GestureInterpreterSetPropProvider_fn(g,&props,nullptr);
        GestureInterpreterInitialize_fn(g,GESTURES_DEVCLASS_TOUCHPAD);
        GestureInterpreterSetHardwareProperties_fn(g,&hw);
        GestureInterpreterSetTimerProvider_fn(g,&timers,nullptr);
        GestureInterpreterSetCallback_fn(g,event,nullptr);
        double time=1;
        auto frame = [&](int id, float x, bool repeat) {
            time += repeat ? .002 : .0041;
            advance(time);
            FingerState finger{}; finger.tracking_id=id; finger.position_x=x; finger.position_y=1000;
            HardwareState state{}; state.timestamp=time; state.msc_timestamp=time-1;
            if (repeat) state.msc_timestamp=policy==1 ? 0 : time-1-.002;
            state.finger_cnt=state.touch_cnt=id ? 1 : 0; state.fingers=id ? &finger : nullptr;
            GestureInterpreterPushHardwareState_fn(g,&state);
            // Repeats occur between consecutive physical reports.
            if (repeat) time -= .002;
        };
        for(int i=0;i<10;++i) frame(0,0,false);
        for(int i=0;i<20;++i) frame(1,1800,false);
        for(int i=0;i<20;++i) frame(0,0,false);
        for(int i=0;i<70;++i) frame(2,1800,false);
        for(int i=0;i<1500;++i) {
            float x=1800+300*sin(i/150.0);
            frame(2,x,false);
            if (policy && i>150 && i%10==0) frame(2,x,true);
        }
        double lift=time+.0041;
        for(int i=0;i<100;++i) frame(0,0,false);
        advance(time+1);
        bool ok=downs==1 && ups==1 && (policy==1 ?
            up_at-down_at<1 && up_at<lift-5 : fabs(up_at-lift)<.000001 && up_at-down_at>6);
        printf("INPUT_REPLAY policy=%d down=%.6f up=%.6f lift=%.6f downs=%u ups=%u pass=%d\n",
               policy,down_at,up_at,lift,downs,ups,ok);
        passed &= ok;
        DeleteGestureInterpreter_fn(g);
    }
    dlclose(lib);
    return passed ? 0 : 1;
}
