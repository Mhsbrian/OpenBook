// SPDX-License-Identifier: GPL-2.0
/*
 * Host test for ptm_plan.h (ANAL-257): the module's PTM clear/restore code against a mock config space.
 *   cc -O2 -Wall -Werror -o ptm_plan_test ptm_plan_test.c && ./ptm_plan_test
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint16_t u16;
typedef uint32_t u32;

#include "../ptm_plan.h"

struct fn {
	const char *name;
	bool d3cold;		/* behind a powered-off link */
	bool sticky;		/* ignores writes to PTM Control */
	u32 ctrl;
};

static struct fn fns[8];
static int log_n;
static char log_buf[32][24];	/* order of PTM Control writes */
static int failures;

static bool m_readable(void *dev)
{
	return !((struct fn *)dev)->d3cold;
}

static int m_read(void *dev, int where, u32 *val)
{
	struct fn *f = dev;

	if (where != 0x100 + OB_PTM_CTRL)
		return 1;
	*val = f->d3cold ? 0xffffffff : f->ctrl;
	return 0;
}

static int m_write(void *dev, int where, u32 val)
{
	struct fn *f = dev;

	if (where != 0x100 + OB_PTM_CTRL)
		return 1;
	snprintf(log_buf[log_n++], sizeof(log_buf[0]), "%s=%x", f->name, val);
	if (!f->sticky && !f->d3cold)
		f->ctrl = val;
	return 0;
}

static const struct ob_ptm_ops ops = { m_readable, m_read, m_write };

static void expect(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	failures += !ok;
}

static bool order_is(const char *const *want, int n)
{
	int i;

	if (log_n != n)
		return false;
	for (i = 0; i < n; i++)
		if (strcmp(log_buf[i], want[i]))
			return false;
	return true;
}

/* Root port 00:02.2 (depth 0), switch upstream 01:00.0 (1), switch downstream 02:01.0 (2), endpoint 03:00.0 (3)
 * and a second root port 00:03.1 with its endpoint 64:00.0; listed in bus order, as pci_get_device() returns them. */
static int setup(struct ob_ptm_fn *f)
{
	static const struct { const char *name; int depth; u32 ctrl; } t[] = {
		{ "rp0", 0, 0x3 }, { "rp1", 0, 0x3 }, { "up", 1, 0x3 }, { "down", 2, 0x1 }, { "ep", 3, 0x101 },
		{ "gpu", 1, 0x1 },
	};
	int i;

	memset(fns, 0, sizeof(fns));
	log_n = 0;
	for (i = 0; i < 6; i++) {
		fns[i].name = t[i].name;
		fns[i].ctrl = t[i].ctrl;
		f[i] = (struct ob_ptm_fn){ .dev = &fns[i], .depth = t[i].depth, .pos = 0x100, .saved = t[i].ctrl };
	}
	return 6;
}

int main(void)
{
	struct ob_ptm_fn f[OB_PTM_MAX];
	int n, i, done;
	bool all_off = true, all_back = true;

	/* 1. Clear deepest first, keep other control bits (granularity), restore parents first. */
	n = setup(f);
	done = ob_ptm_clear(&ops, f, n);
	{
		static const char *const want[] = { "ep=100", "down=0", "up=0", "gpu=0", "rp0=0", "rp1=0" };

		expect(done == 6 && order_is(want, 6), "clear: endpoint first, root ports last, granularity kept");
	}
	for (i = 0; i < 6; i++)
		all_off &= !(fns[i].ctrl & (OB_PTM_CTRL_ENABLE | OB_PTM_CTRL_ROOT));
	expect(all_off, "clear: Enable and Root Select off everywhere");
	log_n = 0;
	done = ob_ptm_restore(&ops, f, n);
	{
		static const char *const want[] = { "rp1=3", "rp0=3", "gpu=1", "up=3", "down=1", "ep=101" };

		expect(done == 6 && order_is(want, 6), "restore: root ports first, endpoint last, exact old values");
	}
	for (i = 0; i < 6; i++)	/* f[] is sorted now; compare through its dev pointer */
		all_back &= ((struct fn *)f[i].dev)->ctrl == f[i].saved;
	expect(all_back, "restore: every function back to its saved value");

	/* 2. A function in D3cold at suspend is not written; one that refuses the write is not restored. */
	n = setup(f);
	fns[5].d3cold = true;	/* gpu */
	fns[0].sticky = true;	/* rp0 */
	done = ob_ptm_clear(&ops, f, n);
	expect(done == 4, "clear: D3cold skipped, refused write not counted");
	for (i = 0; i < n; i++)
		if (f[i].dev == &fns[5] || f[i].dev == &fns[0])
			expect(!f[i].cleared, "clear: skipped functions are not marked cleared");
	log_n = 0;
	fns[5].d3cold = false;
	done = ob_ptm_restore(&ops, f, n);
	expect(done == 4 && log_n == 4, "restore: only the four cleared functions are written");

	/* 3. A function that is unreachable at resume is left alone; one that already has PTM on again is too. */
	n = setup(f);
	ob_ptm_clear(&ops, f, n);
	fns[4].d3cold = true;			/* ep went away behind its link */
	fns[2].ctrl = OB_PTM_CTRL_ENABLE;	/* up: something turned it back on */
	log_n = 0;
	done = ob_ptm_restore(&ops, f, n);
	expect(done == 4 && log_n == 4, "restore: unreachable and already-enabled functions untouched");

	/* 4. Nothing to do. */
	log_n = 0;
	expect(ob_ptm_clear(&ops, f, 0) == 0 && ob_ptm_restore(&ops, f, 0) == 0 && log_n == 0, "empty list");

	printf("%s: %d failure(s)\n", failures ? "FAILED" : "PASSED", failures);
	return failures != 0;
}
