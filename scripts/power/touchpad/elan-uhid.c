// SPDX-License-Identifier: Apache-2.0
// elan-uhid: a test touchpad for QEMU (ANAL-178). Creates a uhid device with the G14's ELAN touchpad report
// descriptor (04F3:3315, captured by the live stick's "save logs" boot, elan-04f3-3315.rdesc.hex), so the kernel's
// own hid-multitouch binds to it exactly as on the laptop, and plays one-finger strokes the way the G14 reports them:
// a report every 4 ms, Scan Time +41 (100 us units) per report, contact released between strokes and a pause longer
// than hid-multitouch's 1 s timestamp resync. It answers the driver's feature requests (contact count maximum and
// button type: 5 contacts, click pad; the Windows certification blob: zeros) and acknowledges its SET_REPORTs.
// Nothing else: no hardware is touched. Needs /dev/uhid (root).
//
// usage: elan-uhid [STROKES [STROKE_MS [PAUSE_MS [MODE [START_MS]]]]]
//   default 4 strokes of 2000 ms, 1500 ms apart, plain, the first one 3000 ms after the device is created
// MODE: plain  each stroke ends with a normal lift-off;
//       palm   each stroke ends with confidence 0 and the tip up: hid-multitouch splits that into an active palm
//              frame and a separate lift-off frame without MSC_TIMESTAMP (mt_release_pending_palms);
//       sticky halfway through each stroke the reports stop for 150 ms with the finger down: hid-multitouch's 100 ms
//              timer releases the contact in a frame without MSC_TIMESTAMP (mt_release_contacts), then the finger
//              comes back.
// Prints "elan-uhid: ..." lines; the last one is "elan-uhid: done: N reports".
#include <errno.h>
#include <fcntl.h>
#include <linux/uhid.h>
#include <math.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "elan_rdesc.h"  // static const uint8_t RDESC[]; generated from elan-04f3-3315.rdesc.hex

#define TOUCHPAD_REPORT 84  // input report 0x54: 42 bytes with its ID (elan-layout in touchpad-qemu.sh's evidence)
#define REPORT_LEN 42

static int fd;
static unsigned answered_get, answered_set;

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static void put_bits(uint8_t *r, int bit, int size, unsigned v) {
    for (int i = 0; i < size; i++, bit++)
        if (v >> i & 1) r[bit / 8] |= 1 << (bit % 8); else r[bit / 8] &= ~(1 << (bit % 8));
}

static void send_event(struct uhid_event *ev) {
    if (write(fd, ev, sizeof *ev) != sizeof *ev) { perror("elan-uhid: write"); exit(1); }
}

// Feature report sizes with their ID byte, from the descriptor (report_bits / 8).
static int feature_len(int id) {
    switch (id) {
    case 2: return 2; case 3: case 5: case 7: return 3; case 6: return 257; case 11: return 131; case 12: return 897;
    case 13: case 14: return 5; default: return 0;
    }
}

static void handle_uhid(int timeout_ms) {
    struct pollfd p = {.fd = fd, .events = POLLIN};
    while (poll(&p, 1, timeout_ms) > 0) {
        struct uhid_event ev, re;
        if (read(fd, &ev, sizeof ev) <= 0) return;
        memset(&re, 0, sizeof re);
        if (ev.type == UHID_GET_REPORT) {
            int id = ev.u.get_report.rnum, n = feature_len(id);
            re.type = UHID_GET_REPORT_REPLY;
            re.u.get_report_reply.id = ev.u.get_report.id;
            re.u.get_report_reply.err = n ? 0 : EIO;
            re.u.get_report_reply.size = n;
            if (n) re.u.get_report_reply.data[0] = id;
            if (id == 2) re.u.get_report_reply.data[1] = 0x05;  // contact count maximum 5, button type 0 (click pad)
            send_event(&re);
            answered_get++;
        } else if (ev.type == UHID_SET_REPORT) {
            re.type = UHID_SET_REPORT_REPLY;
            re.u.set_report_reply.id = ev.u.set_report.id;
            re.u.set_report_reply.err = 0;
            send_event(&re);
            answered_set++;
        } else if (ev.type == UHID_START) {
            printf("elan-uhid: started by the kernel\n");
        } else if (ev.type == UHID_OPEN) {
            printf("elan-uhid: opened\n");
        }
        timeout_ms = 0;
    }
}

int main(int argc, char **argv) {
    int strokes = argc > 1 ? atoi(argv[1]) : 4, stroke_ms = argc > 2 ? atoi(argv[2]) : 2000;
    int pause_ms = argc > 3 ? atoi(argv[3]) : 1500;
    const char *mode = argc > 4 ? argv[4] : "plain";
    int palm = !strcmp(mode, "palm"), sticky = !strcmp(mode, "sticky");
    int start_ms = argc > 5 ? atoi(argv[5]) : 3000;
    setvbuf(stdout, NULL, _IOLBF, 0);
    fd = open("/dev/uhid", O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("elan-uhid: /dev/uhid"); return 1; }
    struct uhid_event ev;
    memset(&ev, 0, sizeof ev);
    ev.type = UHID_CREATE2;
    snprintf((char *)ev.u.create2.name, sizeof ev.u.create2.name, "OpenBook test ELAN 04F3:3315");
    snprintf((char *)ev.u.create2.phys, sizeof ev.u.create2.phys, "uhid-openbook-test");
    ev.u.create2.rd_size = sizeof RDESC;
    memcpy(ev.u.create2.rd_data, RDESC, sizeof RDESC);
    ev.u.create2.bus = 0x18;  // BUS_I2C, as on the laptop
    ev.u.create2.vendor = 0x04f3;
    ev.u.create2.product = 0x3315;
    ev.u.create2.version = 0x0100;
    send_event(&ev);
    printf("elan-uhid: created (descriptor %zu bytes)\n", sizeof RDESC);
    // START_MS (3 s by default) for the probe (the driver's feature requests) and for Android to open and configure
    // the new input devices, as it has long before anyone touches a built-in touchpad. handle_uhid() returns once the
    // queue is empty.
    for (double end = now_ms() + start_ms; now_ms() < end;) handle_uhid((int)(end - now_ms()) + 1);

    unsigned scan = 0, reports = 0;
    for (int s = 0; s < strokes; s++) {
        int frames = stroke_ms / 4;
        double t = now_ms();
        for (int f = 0; f <= frames + 1; f++) {
            uint8_t r[REPORT_LEN] = {TOUCHPAD_REPORT};
            int down = f <= frames;  // the last report releases the contact
            double a = 2 * M_PI * f / frames;
            unsigned x = 1950 + (unsigned)lround(900 * cos(a + s)), y = 1190 + (unsigned)lround(600 * sin(a + s));
            scan = (scan + 41) & 0xffff;
            put_bits(r, 12, 4, 1);               // contact count
            put_bits(r, 16, 16, scan);           // scan time
            put_bits(r, 32, 1, !(palm && !down)); // confidence: 0 on a palm's lift-off
            put_bits(r, 33, 1, down);            // tip switch
            put_bits(r, 36, 4, s & 15);          // contact id
            put_bits(r, 40, 16, x);
            put_bits(r, 56, 16, y);
            memset(&ev, 0, sizeof ev);
            ev.type = UHID_INPUT2;
            ev.u.input2.size = REPORT_LEN;
            memcpy(ev.u.input2.data, r, REPORT_LEN);
            send_event(&ev);
            reports++;
            t += 4;
            if (sticky && f == frames / 2) t += 150;  // no reports for 150 ms, finger down
            double wait = t - now_ms();
            handle_uhid(wait > 0 ? (int)wait : 0);
            if (wait > 0) { struct timespec ts = {0, (long)((t - now_ms()) * 1e6)}; if (ts.tv_nsec > 0) nanosleep(&ts, NULL); }
        }
        printf("elan-uhid: stroke %d (%s): %d reports\n", s + 1, mode, frames + 2);
        handle_uhid(pause_ms);
    }
    memset(&ev, 0, sizeof ev);
    ev.type = UHID_DESTROY;
    send_event(&ev);
    printf("elan-uhid: done: %u reports, %u GET_REPORT and %u SET_REPORT answered\n", reports, answered_get,
           answered_set);
    return 0;
}
