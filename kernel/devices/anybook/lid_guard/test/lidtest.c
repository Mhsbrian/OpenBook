// SPDX-License-Identifier: GPL-2.0
/*
 * VM functional test for openbook_lid_guard (ANAL-235). Runs as PID 1's child
 * in a throwaway QEMU guest: creates a virtual lid switch with uinput, enters
 * suspend twice (S3 in QEMU, RTC alarm wake), and counts KEY_WAKEUP events that
 * QEMU's ACPI power button delivers after each resume: once with the lid
 * reported closed, once with it open.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static int find_power_button(void)
{
	char path[64], phys[128];

	for (int i = 0; i < 64; i++) {
		snprintf(path, sizeof(path), "/dev/input/event%d", i);
		int fd = open(path, O_RDONLY | O_NONBLOCK);

		if (fd < 0)
			continue;
		memset(phys, 0, sizeof(phys));
		if (ioctl(fd, EVIOCGPHYS(sizeof(phys) - 1), phys) >= 0 &&
		    (!strncmp(phys, "LNXPWRBN/", 9) || !strncmp(phys, "PNP0C0C/", 8))) {
			printf("power button: %s phys=%s\n", path, phys);
			return fd;
		}
		close(fd);
	}
	return -1;
}

static void emit(int fd, int type, int code, int value)
{
	struct input_event ev = { .type = type, .code = code, .value = value };

	if (write(fd, &ev, sizeof(ev)) != sizeof(ev))
		perror("uinput write");
}

static void set_lid(int fd, int closed)
{
	emit(fd, EV_SW, SW_LID, closed);
	emit(fd, EV_SYN, SYN_REPORT, 0);
}

static int make_lid(int closed)
{
	struct uinput_setup setup = { .id = { .bustype = BUS_VIRTUAL, .vendor = 0x1d6b, .product = 0x0235 } };
	int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);

	if (fd < 0)
		return -1;
	ioctl(fd, UI_SET_EVBIT, EV_SW);
	ioctl(fd, UI_SET_SWBIT, SW_LID);
	ioctl(fd, UI_SET_PHYS, "OPENBOOKTEST/lid");
	strcpy(setup.name, "Test Lid Switch");
	if (ioctl(fd, UI_DEV_SETUP, &setup) || ioctl(fd, UI_DEV_CREATE)) {
		perror("uinput create");
		return -1;
	}
	usleep(300000);
	set_lid(fd, closed);
	return fd;
}

static int write_file(const char *path, const char *text)
{
	int fd = open(path, O_WRONLY);
	ssize_t n;

	if (fd < 0)
		return -errno;
	n = write(fd, text, strlen(text));
	n = n < 0 ? -errno : 0;
	close(fd);
	return (int)n;
}

/* Returns KEY_WAKEUP presses seen within 1.5 s of resume, or -1 if suspend failed. */
static int suspend_cycle(int pb, const char *closed_label)
{
	struct input_event ev;
	int presses = 0, err;

	while (read(pb, &ev, sizeof(ev)) == sizeof(ev))
		;
	write_file("/sys/class/rtc/rtc0/wakealarm", "0");
	if ((err = write_file("/sys/class/rtc/rtc0/wakealarm", "+3"))) {
		printf("wakealarm failed: %d\n", err);
		return -1;
	}
	/* QEMU's RTC alarm wakes S3 but not suspend-to-idle; both resume through
	 * the same device callbacks, including acpi_button_resume(). */
	write_file("/sys/power/mem_sleep", getenv("MEM_SLEEP") ? getenv("MEM_SLEEP") : "deep");
	printf("suspending (lid %s)\n", closed_label);
	fflush(stdout);
	if ((err = write_file("/sys/power/state", "mem"))) {
		printf("suspend failed: %d\n", err);
		return -1;
	}
	printf("resumed\n");
	fflush(stdout);
	for (int waited = 0; waited < 1500; waited += 100) {
		struct pollfd p = { .fd = pb, .events = POLLIN };

		poll(&p, 1, 100);
		while (read(pb, &ev, sizeof(ev)) == sizeof(ev))
			if (ev.type == EV_KEY && ev.code == KEY_WAKEUP && ev.value == 1)
				presses++;
	}
	return presses;
}

static int find_by_phys(const char *prefix)
{
	char path[64], phys[128];

	for (int i = 0; i < 64; i++) {
		snprintf(path, sizeof(path), "/dev/input/event%d", i);
		int fd = open(path, O_RDONLY | O_NONBLOCK);

		if (fd < 0)
			continue;
		memset(phys, 0, sizeof(phys));
		if (ioctl(fd, EVIOCGPHYS(sizeof(phys) - 1), phys) >= 0 && !strncmp(phys, prefix, strlen(prefix)))
			return fd;
		close(fd);
	}
	return -1;
}

static double now_s(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

/* ACPI lid whose _LID reads open for 0.5 s after each resume (test SSDT). */
static int acpi_lid_scenario(const char *label)
{
	unsigned long sw[1] = { 0 };
	struct input_event ev;
	int lid = find_by_phys("PNP0C0D/"), pb = find_power_button(), wake = 0, err;
	double t0;

	if (lid < 0 || pb < 0) {
		printf("RESULT %s error=no-acpi-lid-or-button\n", label);
		return 1;
	}
	ioctl(lid, EVIOCGSW(sizeof(sw)), sw);
	printf("acpi lid before suspend: %s\n", (sw[0] >> SW_LID) & 1 ? "closed" : "open");
	while (read(lid, &ev, sizeof(ev)) == sizeof(ev))
		;
	while (read(pb, &ev, sizeof(ev)) == sizeof(ev))
		;
	write_file("/sys/class/rtc/rtc0/wakealarm", "0");
	write_file("/sys/class/rtc/rtc0/wakealarm", "+3");
	write_file("/sys/power/mem_sleep", "deep");
	if ((err = write_file("/sys/power/state", "mem"))) {
		printf("RESULT %s error=suspend-%d\n", label, err);
		return 1;
	}
	t0 = now_s();
	printf("LIDSEQ %s:", label);
	while (now_s() - t0 < 7.0) {
		struct pollfd p[2] = { { .fd = lid, .events = POLLIN }, { .fd = pb, .events = POLLIN } };

		poll(p, 2, 100);
		while (read(lid, &ev, sizeof(ev)) == sizeof(ev))
			if (ev.type == EV_SW && ev.code == SW_LID)
				printf(" %s@%.1fs", ev.value ? "closed" : "open", now_s() - t0);
		while (read(pb, &ev, sizeof(ev)) == sizeof(ev))
			if (ev.type == EV_KEY && ev.code == KEY_WAKEUP && ev.value == 1)
				wake++;
	}
	ioctl(lid, EVIOCGSW(sizeof(sw)), sw);
	printf("\nRESULT %s final_lid=%s key_wakeups=%d\n", label, (sw[0] >> SW_LID) & 1 ? "closed" : "open", wake);
	close(lid);
	close(pb);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc > 2 && !strcmp(argv[2], "acpilid"))
		return acpi_lid_scenario(argv[1]);

	const char *label = argc > 1 ? argv[1] : "run";
	int pb = find_power_button(), lid, closed, open_;

	if (pb < 0) {
		printf("RESULT %s error=no-acpi-power-button\n", label);
		return 1;
	}
	lid = make_lid(1);
	if (lid < 0) {
		printf("RESULT %s error=no-uinput\n", label);
		return 1;
	}
	sleep(1);
	closed = suspend_cycle(pb, "closed");
	set_lid(lid, 0);
	sleep(1);
	open_ = suspend_cycle(pb, "open");
	printf("RESULT %s closed_lid_wakeups=%d open_lid_wakeups=%d\n", label, closed, open_);
	ioctl(lid, UI_DEV_DESTROY);
	close(lid);
	close(pb);
	return 0;
}
