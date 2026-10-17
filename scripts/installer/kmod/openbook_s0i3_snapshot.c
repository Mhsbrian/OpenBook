// SPDX-License-Identifier: GPL-2.0
/*
 * openbook_s0i3_snapshot: test-only module for the OpenBook hardware check (ANAL-178). Never part of an image.
 *
 * Why the GA403WR misses S0i3 under our kernel is not visible from userspace: everything the probe can read is taken
 * before the system suspend starts, while drivers only put their devices into D3 during it. This module registers an
 * LPS0 device hook, the interface amd_pmc uses. Its prepare callback runs in the s2idle path after every device has
 * finished its noirq suspend and after the LPS0 "screen off" and "entry" _DSM calls, right before the CPUs go idle
 * and the SoC may enter S0i3. At that moment it logs every PCI function that is not in D3:
 *   - the kernel's view (pci_dev->current_state) and, where it is safe to read, the hardware's (PMCSR state bits);
 *   - skip_bus_pm, which the PCI core sets on a function that stayed in D0 and on that function's parent bridge, so
 *     a driverless function also keeps its bridge in D0 (drivers/pci/pci-driver.c, pci_pm_suspend_noirq());
 *   - the bound driver and the ACPI companion's power state.
 * restore logs the same on the way out, plus how many times the s2idle loop woke to check for a wakeup.
 *
 * all=1 logs every PCI function, not only those not in D3. Nothing is changed; for this boot only.
 */
#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/acpi.h>
#include <linux/module.h>
#include <linux/pci.h>

static bool all;
module_param(all, bool, 0644);
MODULE_PARM_DESC(all, "log every PCI function, not only those not in D3");

static unsigned int checks;

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

/* Config space is only read when the function and the bridge above it are not in D3cold: behind a powered-off link
 * a config read cannot reach the function. */
static bool readable(struct pci_dev *pdev)
{
	struct pci_dev *up = pci_upstream_bridge(pdev);

	return pdev->current_state != PCI_D3cold && !(up && up->current_state == PCI_D3cold);
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

/* Link power: ASPM L0s/L1 enables (Link Control), L1 PM substate enables (L1SS Control 1) and PTM enable. Linux
 * 7.2 (CONFIG_PCIE_PTM=y) enables PTM on root ports and disables it again at suspend; our kernel has no PTM support,
 * so whatever the firmware set stays. */
static void link_state(struct pci_dev *pdev, char *buf, size_t len)
{
	u16 lnkctl = 0;
	u32 l1ss = 0, ptm = 0;
	int pos;

	buf[0] = 0;
	if (!pci_is_pcie(pdev) || !readable(pdev))
		return;
	pcie_capability_read_word(pdev, PCI_EXP_LNKCTL, &lnkctl);
	pos = pci_find_ext_capability(pdev, PCI_EXT_CAP_ID_L1SS);
	if (pos)
		pci_read_config_dword(pdev, pos + PCI_L1SS_CTL1, &l1ss);
	pos = pci_find_ext_capability(pdev, PCI_EXT_CAP_ID_PTM);
	if (pos)
		pci_read_config_dword(pdev, pos + PCI_PTM_CTRL, &ptm);
	snprintf(buf, len, " aspm%s%s%s l1ss %#x%s", lnkctl & PCI_EXP_LNKCTL_ASPM_L0S ? " L0s" : "",
		 lnkctl & PCI_EXP_LNKCTL_ASPM_L1 ? " L1" : "", lnkctl & PCI_EXP_LNKCTL_ASPMC ? "" : " off",
		 l1ss & PCI_L1SS_CTL1_L1SS_MASK, ptm & PCI_PTM_CTRL_ENABLE ? " ptm on" : "");
}

static void snapshot(const char *when)
{
	struct pci_dev *pdev = NULL;
	int n = 0, awake = 0;

	while ((pdev = pci_get_device(PCI_ANY_ID, PCI_ANY_ID, pdev))) {
		struct acpi_device *adev = ACPI_COMPANION(&pdev->dev);
		bool in_d3 = pdev->current_state >= PCI_D3hot && pdev->current_state <= PCI_D3cold;
		char hw[16], link[64], acpi[48] = "";

		n++;
		if (!in_d3)
			awake++;
		if (!all && in_d3)
			continue;
		hw_state(pdev, hw, sizeof(hw));
		link_state(pdev, link, sizeof(link));
		if (adev && adev->flags.power_manageable)
			snprintf(acpi, sizeof(acpi), " acpi %s", acpi_state(adev->power.state));
		pr_info("%s: %s %04x:%04x class %06x kernel %s pmcsr %s driver %s%s%s%s\n", when, pci_name(pdev),
			pdev->vendor, pdev->device, pdev->class, pci_state(pdev->current_state), hw,
			pdev->dev.driver ? pdev->dev.driver->name : "-", pdev->skip_bus_pm ? " skip_bus_pm" : "", link,
			acpi);
	}
	pr_info("%s: %d PCI functions, %d not in D3\n", when, n, awake);
}

static void ob_prepare(void)
{
	checks = 0;
	snapshot("s0i3-entry");
}

static void ob_check(void)
{
	checks++;
}

static void ob_restore(void)
{
	pr_info("s0i3-exit: the s2idle loop checked for a wakeup %u time(s)\n", checks);
	snapshot("s0i3-exit");
}

static struct acpi_s2idle_dev_ops ob_ops = {
	.prepare = ob_prepare,
	.check = ob_check,
	.restore = ob_restore,
};

static int __init openbook_s0i3_snapshot_init(void)
{
	int ret = acpi_register_lps0_dev(&ob_ops);

	if (ret)
		pr_info("no LPS0 device to hook into (%d)\n", ret);
	else
		pr_info("registered: PCI power states will be logged at s2idle entry and exit%s\n",
			all ? " (all functions)" : "");
	return ret;
}

static void __exit openbook_s0i3_snapshot_exit(void)
{
	acpi_unregister_lps0_dev(&ob_ops);
}

module_init(openbook_s0i3_snapshot_init);
module_exit(openbook_s0i3_snapshot_exit);
MODULE_DESCRIPTION("OpenBook hardware check: log PCI power states at s2idle entry (test only)");
MODULE_LICENSE("GPL");
