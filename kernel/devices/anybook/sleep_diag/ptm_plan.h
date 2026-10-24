/* SPDX-License-Identifier: GPL-2.0 */
/*
 * PTM clear/restore order for openbook_sleep_diag (ANAL-257). Kept free of kernel headers so that
 * test/ptm_plan_test.c can run the same code against a mock config space on the host.
 *
 * Linux (CONFIG_PCIE_PTM=y) turns PTM off in pci_pm_suspend() on every function where a driver enabled it,
 * children before parents because that is the device suspend order, and back on at resume, parents first. The GKI
 * has CONFIG_PCIE_PTM off, so whatever the firmware enabled stays enabled through s2idle. This applies Linux's
 * order to every function with PTM on, from a PM notifier: clear Enable and Root Select deepest function first,
 * then restore in the opposite order.
 */
#ifndef OPENBOOK_PTM_PLAN_H
#define OPENBOOK_PTM_PLAN_H

#define OB_PTM_CTRL		0x08	/* PCI_PTM_CTRL */
#define OB_PTM_CTRL_ENABLE	0x01	/* PCI_PTM_CTRL_ENABLE */
#define OB_PTM_CTRL_ROOT	0x02	/* PCI_PTM_CTRL_ROOT */
#define OB_PTM_MAX		64

struct ob_ptm_fn {
	void *dev;		/* struct pci_dev * in the module */
	int depth;		/* bridges between the function and the root bus */
	u16 pos;		/* offset of the PTM extended capability */
	u32 saved;		/* PTM Control as found before suspend */
	bool cleared;		/* we cleared it and must restore it */
};

struct ob_ptm_ops {
	bool (*readable)(void *dev);	/* false behind a powered-off link (D3cold) */
	int (*read)(void *dev, int where, u32 *val);
	int (*write)(void *dev, int where, u32 val);
};

/* Deepest first; stable, so functions at the same depth keep bus order. n is at most OB_PTM_MAX. */
static void ob_ptm_sort(struct ob_ptm_fn *f, int n)
{
	int i, j;

	for (i = 1; i < n; i++) {
		struct ob_ptm_fn t = f[i];

		for (j = i; j > 0 && f[j - 1].depth < t.depth; j--)
			f[j] = f[j - 1];
		f[j] = t;
	}
}

/*
 * f[] holds the functions whose PTM Control had Enable set (saved). Sorts them, clears Enable and Root Select
 * deepest first and reads each one back. Returns how many are now off; a function that does not take the write
 * is left marked not cleared, so restore never touches it.
 */
static int ob_ptm_clear(const struct ob_ptm_ops *ops, struct ob_ptm_fn *f, int n)
{
	int i, done = 0;
	u32 v;

	ob_ptm_sort(f, n);
	for (i = 0; i < n; i++) {
		f[i].cleared = false;
		if (!ops->readable(f[i].dev))
			continue;
		if (ops->write(f[i].dev, f[i].pos + OB_PTM_CTRL,
			       f[i].saved & ~(u32)(OB_PTM_CTRL_ENABLE | OB_PTM_CTRL_ROOT)))
			continue;
		if (ops->read(f[i].dev, f[i].pos + OB_PTM_CTRL, &v) || (v & OB_PTM_CTRL_ENABLE))
			continue;
		f[i].cleared = true;
		done++;
	}
	return done;
}

/*
 * Puts back the saved value, parents first (the reverse of ob_ptm_clear's order), on every function we cleared that
 * is reachable and still has Enable off. A function that went through D3cold came back with PTM reset to off; it
 * gets its old value back too, as pci_resume_ptm() would. Returns how many were restored.
 */
static int ob_ptm_restore(const struct ob_ptm_ops *ops, struct ob_ptm_fn *f, int n)
{
	int i, done = 0;
	u32 v;

	for (i = n - 1; i >= 0; i--) {
		if (!f[i].cleared || !ops->readable(f[i].dev))
			continue;
		if (ops->read(f[i].dev, f[i].pos + OB_PTM_CTRL, &v) || v == 0xffffffff || (v & OB_PTM_CTRL_ENABLE))
			continue;
		if (ops->write(f[i].dev, f[i].pos + OB_PTM_CTRL, f[i].saved))
			continue;
		if (!ops->read(f[i].dev, f[i].pos + OB_PTM_CTRL, &v) && v == f[i].saved)
			done++;
	}
	return done;
}

#endif
