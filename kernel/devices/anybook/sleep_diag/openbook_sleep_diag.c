// SPDX-License-Identifier: GPL-2.0
/*
 * openbook_sleep_diag: S0i3 diagnostics for the G14 under the Googlebook (Ruby) image (ANAL-257). Test only.
 *
 * It ships in vendor_dlkm but in no load list: the G14 lab helper loads it with parameters for one experiment and
 * unloads it afterwards (docs/googlebook-s0i3.md). Loaded without parameters it logs one "inactive" line and does
 * nothing.
 *
 *   ptm_off=1   Clear PTM Enable and Root Select on every PCI function before each suspend and restore them after
 *               (ptm_plan.h). The GKI has CONFIG_PCIE_PTM off, so whatever the firmware enabled stays enabled
 *               through s2idle. Linux 7.2 does the same on this laptop: since v7.1 (e1092d5e15e6) it no longer
 *               enables PTM itself, and pci_suspend_ptm() only undoes what a driver enabled. So this does not copy
 *               Linux; it tests whether the firmware's PTM settings matter at all.
 *   snapshot=1  At the S0i3 attempt (LPS0 prepare: every device has finished its noirq suspend, right before the
 *               CPUs go idle) and on the way out, log every PCI function not in D3: kernel and hardware D-state,
 *               runtime PM, driver, ASPM, L1 substates, link status, LTR, PTM, ACPI power state.
 *   snapshot=2  The same for every PCI function.
 *   usb4=1      The USB4 host routers (class 0c0340) and the thunderbolt devices below them: runtime PM, D-state,
 *               wakeup and ACPI state, at load, 60 s later and at every suspend.
 *   cycles=N    Full logs for the first N suspends (default 3). Later ones get one summary line each, so a day of
 *               Android autosuspend does not push the boot out of the kernel log.
 *
 * With any of them set, every function with a PTM capability is also listed once at load, with what the firmware
 * left enabled. Nothing is written to any device except PTM Control, and only with ptm_off=1.
 *
 * report (read only) holds the last S0i3 attempt in a few lines: the counts, every PCI function not in D3 and the
 * USB4 routers' state. A user build's adb shell cannot read the kernel log, so the lab helper (openbook-pc-setup
 * lab report) reads /sys/module/openbook_sleep_diag/parameters/report and copies it to logcat.
 */
#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/acpi.h>
#include <linux/module.h>
#include <linux/spinlock.h>
#include <linux/pci.h>
#include <linux/pm_runtime.h>
#include <linux/suspend.h>
#include <linux/workqueue.h>

#include "ptm_plan.h"

/* USB4 host interface; drivers/thunderbolt/nhi.h has the same, include/linux/pci_ids.h does not yet. */
#define OB_CLASS_USB4	0x0c0340

static bool ptm_off;
module_param(ptm_off, bool, 0444);
MODULE_PARM_DESC(ptm_off, "clear PTM on every PCI function across suspend, as Linux does");

static unsigned int snapshot;
module_param(snapshot, uint, 0444);
MODULE_PARM_DESC(snapshot, "log PCI power state at the S0i3 attempt: 1 = functions not in D3, 2 = all");

static bool usb4;
module_param(usb4, bool, 0444);
MODULE_PARM_DESC(usb4, "log the USB4 host routers' runtime PM state");

static unsigned int cycles = 3;
module_param(cycles, uint, 0444);
MODULE_PARM_DESC(cycles, "full logs for the first N suspends, one line each after that");

#define OB_REPORT_LEN 3072
static char report_buf[OB_REPORT_LEN] = "no S0i3 attempt yet\n";
static size_t report_len;
static DEFINE_SPINLOCK(report_lock);

static __printf(1, 2) void report_add(const char *fmt, ...)
{
	unsigned long flags;
	va_list args;

	spin_lock_irqsave(&report_lock, flags);
	va_start(args, fmt);
	report_len += vscnprintf(report_buf + report_len, sizeof(report_buf) - report_len, fmt, args);
	va_end(args);
	spin_unlock_irqrestore(&report_lock, flags);
}

static void report_reset(void)
{
	unsigned long flags;

	spin_lock_irqsave(&report_lock, flags);
	report_len = 0;
	report_buf[0] = 0;
	spin_unlock_irqrestore(&report_lock, flags);
}

static int report_get(char *buf, const struct kernel_param *kp)
{
	unsigned long flags;
	int n;

	spin_lock_irqsave(&report_lock, flags);
	n = scnprintf(buf, PAGE_SIZE, "%s", report_buf);
	spin_unlock_irqrestore(&report_lock, flags);
	return n;
}

static const struct kernel_param_ops report_ops = {
	.get = report_get,
};
module_param_cb(report, &report_ops, NULL, 0444);
MODULE_PARM_DESC(report, "the last S0i3 attempt: counts, PCI functions not in D3, USB4 routers (read only)");

static unsigned int attempts;	/* PM_SUSPEND_PREPARE notifications */
static unsigned int entries;	/* LPS0 prepare calls: the s2idle path reached the S0i3 attempt */
static unsigned int checks;
static struct ob_ptm_fn ptm[OB_PTM_MAX];
static int ptm_n;
static bool pm_registered, lps0_registered;

static const char *pci_state(pci_power_t s)
{
	static const char *const names[] = { "D0", "D1", "D2", "D3hot", "D3cold" };

	return s >= PCI_D0 && s <= PCI_D3cold ? names[s] : "unknown";
}

static const char *acpi_state(int s)
{
	static const char *const names[] = { "D0", "D1", "D2", "D3hot", "D3cold" };

	return s >= ACPI_STATE_D0 && s <= ACPI_STATE_D3_COLD ? names[s] : "unknown";
}

static const char *rpm_state(struct device *dev)
{
	if (!pm_runtime_enabled(dev))
		return "disabled";
	switch (dev->power.runtime_status) {
	case RPM_ACTIVE:
		return "active";
	case RPM_RESUMING:
		return "resuming";
	case RPM_SUSPENDED:
		return "suspended";
	case RPM_SUSPENDING:
		return "suspending";
	default:
		return "other";
	}
}

static const char *pcie_type(struct pci_dev *pdev)
{
	if (!pci_is_pcie(pdev))
		return "pci";
	switch (pci_pcie_type(pdev)) {
	case PCI_EXP_TYPE_ENDPOINT:
		return "endpoint";
	case PCI_EXP_TYPE_LEG_END:
		return "legacy-endpoint";
	case PCI_EXP_TYPE_ROOT_PORT:
		return "root-port";
	case PCI_EXP_TYPE_UPSTREAM:
		return "switch-up";
	case PCI_EXP_TYPE_DOWNSTREAM:
		return "switch-down";
	case PCI_EXP_TYPE_RC_END:
		return "rc-endpoint";
	case PCI_EXP_TYPE_RC_EC:
		return "rc-collector";
	default:
		return "pcie";
	}
}

/* Config space is only touched when the function and the bridge above it are not in D3cold: behind a powered-off
 * link a config request cannot reach the function. When a bridge enters D3cold the PCI core marks everything below
 * it D3cold too, so the parent is the only one to check. */
static bool readable(struct pci_dev *pdev)
{
	struct pci_dev *up = pci_upstream_bridge(pdev);

	return pdev->current_state != PCI_D3cold && !(up && up->current_state == PCI_D3cold);
}

static u16 ptm_pos(struct pci_dev *pdev)
{
	return pci_is_pcie(pdev) ? pci_find_ext_capability(pdev, PCI_EXT_CAP_ID_PTM) : 0;
}

static int depth(struct pci_dev *pdev)
{
	struct pci_bus *bus;
	int d = 0;

	for (bus = pdev->bus; bus->parent; bus = bus->parent)
		d++;
	return d;
}

static bool ops_readable(void *dev)
{
	return readable(dev);
}

static int ops_read(void *dev, int where, u32 *val)
{
	return pci_read_config_dword(dev, where, val);
}

static int ops_write(void *dev, int where, u32 val)
{
	return pci_write_config_dword(dev, where, val);
}

static const struct ob_ptm_ops ptm_ops = {
	.readable = ops_readable,
	.read = ops_read,
	.write = ops_write,
};

/* Every function with a PTM capability; at load this is what the firmware left enabled. */
static void ptm_list(const char *when, bool verbose)
{
	struct pci_dev *pdev = NULL;
	int n = 0, on = 0;

	while ((pdev = pci_get_device(PCI_ANY_ID, PCI_ANY_ID, pdev))) {
		u32 cap = 0, ctrl = 0;
		u16 pos;

		if (!readable(pdev) || !(pos = ptm_pos(pdev)))
			continue;
		pci_read_config_dword(pdev, pos + PCI_PTM_CAP, &cap);
		pci_read_config_dword(pdev, pos + PCI_PTM_CTRL, &ctrl);
		n++;
		if (ctrl != ~0u && (ctrl & PCI_PTM_CTRL_ENABLE))
			on++;
		if (verbose)
			pr_info("%s: %s %04x:%04x %s ptm cap %#x%s%s%s ctrl %#x%s%s\n", when, pci_name(pdev),
				pdev->vendor, pdev->device, pcie_type(pdev), cap,
				cap & PCI_PTM_CAP_REQ ? " requester" : "", cap & PCI_PTM_CAP_RES ? " responder" : "",
				cap & PCI_PTM_CAP_ROOT ? " root" : "", ctrl,
				ctrl & PCI_PTM_CTRL_ENABLE ? " enabled" : " disabled",
				ctrl & PCI_PTM_CTRL_ROOT ? " root-select" : "");
	}
	pr_info("%s: %d function(s) with a PTM capability, %d with PTM enabled\n", when, n, on);
}

static void ptm_release(void)
{
	while (ptm_n > 0) {
		ptm_n--;
		pci_dev_put(ptm[ptm_n].dev);
		ptm[ptm_n].dev = NULL;
	}
}

/* Record every reachable function with PTM Enable set, holding a reference until the resume. */
static int ptm_collect(void)
{
	struct pci_dev *pdev = NULL;
	int n = 0;

	ptm_release();
	while ((pdev = pci_get_device(PCI_ANY_ID, PCI_ANY_ID, pdev))) {
		u32 ctrl;
		u16 pos;

		if (!readable(pdev) || !(pos = ptm_pos(pdev)))
			continue;
		if (pci_read_config_dword(pdev, pos + PCI_PTM_CTRL, &ctrl) || ctrl == ~0u ||
		    !(ctrl & PCI_PTM_CTRL_ENABLE))
			continue;
		if (n == OB_PTM_MAX) {
			pr_warn("suspend %u: more than %d functions have PTM on; %s keeps it\n", attempts,
				OB_PTM_MAX, pci_name(pdev));
			continue;
		}
		ptm[n].dev = pci_dev_get(pdev);
		ptm[n].depth = depth(pdev);
		ptm[n].pos = pos;
		ptm[n].saved = ctrl;
		n++;
	}
	ptm_n = n;
	return n;
}

static void ptm_suspend(bool verbose)
{
	int n = ptm_collect(), off, i;

	off = ob_ptm_clear(&ptm_ops, ptm, n);
	for (i = 0; verbose && i < n; i++)
		pr_info("suspend %u: ptm %s %s depth %d ctrl %#x -> %s\n", attempts, pci_name(ptm[i].dev),
			pcie_type(ptm[i].dev), ptm[i].depth, ptm[i].saved, ptm[i].cleared ? "off" : "NOT CLEARED");
	if (verbose || off != n)
		pr_info("suspend %u: PTM turned off on %d of %d function(s) that had it on\n", attempts, off, n);
}

static void ptm_resume(bool verbose)
{
	int back = ob_ptm_restore(&ptm_ops, ptm, ptm_n), want = 0, i;

	for (i = 0; i < ptm_n; i++)
		want += ptm[i].cleared;
	ptm_release();
	if (verbose || back != want)
		pr_info("resume %u: PTM restored on %d of %d function(s)\n", attempts, back, want);
}

/* Link power and PTM: ASPM L0s/L1 (Link Control), L1 PM substates (L1SS Control 1), Link Status, LTR enable
 * (Device Control 2) and PTM Enable. */
static void link_state(struct pci_dev *pdev, char *buf, size_t len, bool *ptm_on)
{
	u16 lnkctl = 0, lnksta = 0, devctl2 = 0, pos;
	u32 l1ss = 0, ptmctl = 0;

	buf[0] = 0;
	*ptm_on = false;
	if (!pci_is_pcie(pdev) || !readable(pdev))
		return;
	pcie_capability_read_word(pdev, PCI_EXP_LNKCTL, &lnkctl);
	pcie_capability_read_word(pdev, PCI_EXP_LNKSTA, &lnksta);
	pcie_capability_read_word(pdev, PCI_EXP_DEVCTL2, &devctl2);
	pos = pci_find_ext_capability(pdev, PCI_EXT_CAP_ID_L1SS);
	if (pos)
		pci_read_config_dword(pdev, pos + PCI_L1SS_CTL1, &l1ss);
	pos = ptm_pos(pdev);
	if (pos)
		pci_read_config_dword(pdev, pos + PCI_PTM_CTRL, &ptmctl);
	*ptm_on = ptmctl != ~0u && (ptmctl & PCI_PTM_CTRL_ENABLE);
	snprintf(buf, len, " aspm%s%s%s l1ss %#x lnksta %#06x%s%s", lnkctl & PCI_EXP_LNKCTL_ASPM_L0S ? " L0s" : "",
		 lnkctl & PCI_EXP_LNKCTL_ASPM_L1 ? " L1" : "", lnkctl & PCI_EXP_LNKCTL_ASPMC ? "" : " off",
		 l1ss & PCI_L1SS_CTL1_L1SS_MASK, lnksta, devctl2 & PCI_EXP_DEVCTL2_LTR_EN ? " ltr" : "",
		 *ptm_on ? " ptm on" : "");
}

static void hw_state(struct pci_dev *pdev, char *buf, size_t len)
{
	u16 pmcsr;

	if (!pdev->pm_cap)
		snprintf(buf, len, "no-pm-cap");
	else if (!readable(pdev))
		snprintf(buf, len, "not-read");
	else if (pci_read_config_word(pdev, pdev->pm_cap + PCI_PM_CTRL, &pmcsr) || pmcsr == 0xffff)
		snprintf(buf, len, "no-response");
	else
		snprintf(buf, len, "%s", pci_state(pmcsr & PCI_PM_CTRL_STATE_MASK));
}

/* One line per function (all, or those not in D3) when verbose, and always a summary line with the counts. */
static void pci_snapshot(const char *when, unsigned int n_when, bool verbose, bool to_report)
{
	struct pci_dev *pdev = NULL;
	int n = 0, awake = 0, ptm_on = 0;

	while ((pdev = pci_get_device(PCI_ANY_ID, PCI_ANY_ID, pdev))) {
		struct acpi_device *adev = ACPI_COMPANION(&pdev->dev);
		bool in_d3 = pdev->current_state >= PCI_D3hot && pdev->current_state <= PCI_D3cold, on;
		char hw[16], link[80], acpi[16] = "";

		n++;
		awake += !in_d3;
		link_state(pdev, link, sizeof(link), &on);
		ptm_on += on;
		if (to_report && (!in_d3 || on))
			report_add("  %s %04x:%04x %s %s%s\n", pci_name(pdev), pdev->vendor, pdev->device,
				   pci_state(pdev->current_state), pdev->dev.driver ? pdev->dev.driver->name : "-",
				   on ? " ptm-on" : "");
		if (!verbose || (snapshot < 2 && in_d3))
			continue;
		hw_state(pdev, hw, sizeof(hw));
		if (adev && adev->flags.power_manageable)
			snprintf(acpi, sizeof(acpi), " acpi %s", acpi_state(adev->power.state));
		pr_info("%s %u: %s %04x:%04x %s kernel %s pmcsr %s rpm %s driver %s%s%s%s%s\n", when, n_when,
			pci_name(pdev), pdev->vendor, pdev->device, pcie_type(pdev), pci_state(pdev->current_state), hw,
			rpm_state(&pdev->dev), pdev->dev.driver ? pdev->dev.driver->name : "-",
			pdev->skip_bus_pm ? " skip_bus_pm" : "", !pdev->d3cold_allowed || pdev->no_d3cold ?
			" no-d3cold" : "", link, acpi);
	}
	pr_info("%s %u: %d PCI functions, %d not in D3, %d with PTM on\n", when, n_when, n, awake, ptm_on);
	if (to_report)
		report_add("s0i3-entry %u: %d PCI functions, %d not in D3, %d with PTM on (listed above)\n", n_when, n,
			   awake, ptm_on);
}

struct usb4_ctx {
	const char *when;
	int level;
};

static int usb4_child(struct device *dev, void *data)
{
	struct usb4_ctx *ctx = data, next = { ctx->when, ctx->level + 1 };

	pr_info("%s: %*s%s rpm %s usage %d%s%s\n", ctx->when, 2 * ctx->level, "", dev_name(dev), rpm_state(dev),
		atomic_read(&dev->power.usage_count), dev->power.runtime_auto ? "" : " control-on",
		device_may_wakeup(dev) ? " wakeup" : "");
	if (ctx->level < 3)
		device_for_each_child(dev, &next, usb4_child);
	return 0;
}

static void usb4_report(const char *when, bool to_log, bool to_report)
{
	struct pci_dev *pdev = NULL;
	int n = 0;

	while ((pdev = pci_get_class(OB_CLASS_USB4, pdev))) {
		struct pci_dev *up = pci_upstream_bridge(pdev);
		struct acpi_device *adev = ACPI_COMPANION(&pdev->dev);
		struct usb4_ctx ctx = { when, 1 };
		char hw[16];

		n++;
		if (to_report)
			report_add("  usb4 %s %s rpm %s; bridge %s %s\n", pci_name(pdev), pci_state(pdev->current_state),
				   rpm_state(&pdev->dev), up ? pci_name(up) : "-", up ? pci_state(up->current_state) : "-");
		if (!to_log)
			continue;
		hw_state(pdev, hw, sizeof(hw));
		pr_info("%s: usb4 %s %04x:%04x driver %s kernel %s pmcsr %s rpm %s usage %d%s%s%s autosuspend %d ms%s; "
			"bridge %s kernel %s rpm %s%s%s\n", when, pci_name(pdev), pdev->vendor, pdev->device,
			pdev->dev.driver ? pdev->dev.driver->name : "-", pci_state(pdev->current_state), hw,
			rpm_state(&pdev->dev), atomic_read(&pdev->dev.power.usage_count),
			pdev->dev.power.runtime_auto ? "" : " control-on", device_may_wakeup(&pdev->dev) ? " wakeup" : "",
			!pdev->d3cold_allowed || pdev->no_d3cold ? " no-d3cold" : "",
			pdev->dev.power.autosuspend_delay,
			adev && adev->flags.power_manageable ? (adev->power.state == ACPI_STATE_D3_COLD ?
								  ", acpi D3cold" : ", acpi not D3cold") : "",
			up ? pci_name(up) : "-", up ? pci_state(up->current_state) : "-", up ? rpm_state(&up->dev) : "-",
			up && up->bridge_d3 ? " bridge-d3" : "", up && up->dev.power.runtime_auto ? "" : " control-on");
		device_for_each_child(&pdev->dev, &ctx, usb4_child);
	}
	if (!n && to_log)
		pr_info("%s: no USB4 host router\n", when);
	if (!n && to_report)
		report_add("  no USB4 host router\n");
}

static void usb4_later(struct work_struct *work)
{
	usb4_report("load+60s", true, false);
}

static DECLARE_DELAYED_WORK(usb4_work, usb4_later);

static int ob_pm(struct notifier_block *nb, unsigned long action, void *data)
{
	bool verbose;

	switch (action) {
	case PM_SUSPEND_PREPARE:
		attempts++;
		verbose = attempts <= cycles;
		if (usb4 && verbose)
			usb4_report("suspend", true, false);
		if (ptm_off)
			ptm_suspend(verbose);
		break;
	case PM_POST_SUSPEND:
		if (ptm_off)
			ptm_resume(attempts <= cycles);
		break;
	}
	return NOTIFY_DONE;
}

static struct notifier_block ob_nb = {
	.notifier_call = ob_pm,
};

static void ob_prepare(void)
{
	entries++;
	checks = 0;
	report_reset();
	report_add("s0i3-entry %u (suspend %u)%s:\n", entries, attempts, ptm_off ? ", PTM off" : "");
	pci_snapshot("s0i3-entry", entries, snapshot && entries <= cycles, true);
	if (usb4)
		usb4_report("s0i3-entry", entries <= cycles, true);
}

static void ob_check(void)
{
	checks++;
}

static void ob_restore(void)
{
	bool verbose = snapshot && entries <= cycles;

	pr_info("s0i3-exit %u: the s2idle loop checked for a wakeup %u time(s)\n", entries, checks);
	if (verbose)
		pci_snapshot("s0i3-exit", entries, true, false);
}

static struct acpi_s2idle_dev_ops ob_ops = {
	.prepare = ob_prepare,
	.check = ob_check,
	.restore = ob_restore,
};

static int __init openbook_sleep_diag_init(void)
{
	int ret;

	if (!ptm_off && !snapshot && !usb4) {
		pr_info("inactive (no openbook_sleep_diag parameter set)\n");
		return 0;
	}
	pr_info("active: ptm_off=%d snapshot=%u usb4=%d cycles=%u\n", ptm_off, snapshot, usb4, cycles);
	ptm_list("load", true);
	if (usb4) {
		usb4_report("load", true, false);
		queue_delayed_work(system_wq, &usb4_work, 60 * HZ);
	}
	ret = register_pm_notifier(&ob_nb);
	if (ret)
		pr_warn("PM notifier not registered (%d): no PTM change, no per-suspend logs\n", ret);
	else
		pm_registered = true;
	ret = acpi_register_lps0_dev(&ob_ops);
	if (ret)
		pr_info("no LPS0 device to hook into (%d): no s0i3-entry logs\n", ret);
	else
		lps0_registered = true;
	return 0;
}

static void __exit openbook_sleep_diag_exit(void)
{
	if (lps0_registered)
		acpi_unregister_lps0_dev(&ob_ops);
	if (pm_registered)
		unregister_pm_notifier(&ob_nb);
	cancel_delayed_work_sync(&usb4_work);
	ptm_release();
}

module_init(openbook_sleep_diag_init);
module_exit(openbook_sleep_diag_exit);
MODULE_DESCRIPTION("OpenBook G14 S0i3 diagnostics: PTM off across suspend, PCI and USB4 power snapshots (test only)");
MODULE_LICENSE("GPL");
