// SPDX-License-Identifier: GPL-2.0
/*
 * openbook_pci_pm: test-only module for the OpenBook hardware check (ANAL-178). Never part of an image.
 *
 * A PCI function with no driver stays in D0 through a system suspend: pci_pm_suspend_noirq() only saves its state.
 * It then also keeps the bridge above it in D0 (skip_bus_pm). On the GA403WR our kernel leaves the AMD PSP
 * (1022:17e0, ccp under Linux) and a dummy function (1022:150d) without a driver; Linux 7.2 on the same laptop binds
 * ccp to the PSP, so the PSP and its bridge can go to D3 there.
 *
 * This driver has no ID table: the hardware check binds it to chosen functions with driver_override for one boot.
 * It does nothing but PCI power management: at the noirq stage of a system suspend it saves the function's state
 * and lets the PCI core pick and set its sleep state (pci_prepare_to_sleep(), what the core does for any function
 * whose driver has PM callbacks), and logs the state it reached. On resume the PCI core powers the function up and
 * restores its configuration as usual. It never enables the function, maps its BARs or touches its registers.
 */
#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/module.h>
#include <linux/pci.h>

static const char *pci_state(pci_power_t s)
{
	static const char *const names[] = { "D0", "D1", "D2", "D3hot", "D3cold" };

	return s >= PCI_D0 && s <= PCI_D3cold ? names[s] : "unknown";
}

static int ob_probe(struct pci_dev *pdev, const struct pci_device_id *id)
{
	pci_info(pdev, "%s: bound for this boot (PCI power management only)\n", KBUILD_MODNAME);
	return 0;
}

static void ob_remove(struct pci_dev *pdev)
{
}

static int ob_suspend_noirq(struct device *dev)
{
	struct pci_dev *pdev = to_pci_dev(dev);
	int ret;

	pci_save_state(pdev);
	ret = pci_prepare_to_sleep(pdev);
	pci_info(pdev, "%s: suspend: %s (%d)\n", KBUILD_MODNAME, pci_state(pdev->current_state), ret);
	return 0;
}

static int ob_resume_noirq(struct device *dev)
{
	pci_info(to_pci_dev(dev), "%s: resume: %s\n", KBUILD_MODNAME, pci_state(to_pci_dev(dev)->current_state));
	return 0;
}

static const struct dev_pm_ops ob_pm = {
	.suspend_noirq = ob_suspend_noirq,
	.resume_noirq = ob_resume_noirq,
};

static struct pci_driver ob_driver = {
	.name = "openbook_pci_pm",
	.id_table = NULL,	/* driver_override only */
	.probe = ob_probe,
	.remove = ob_remove,
	.driver.pm = &ob_pm,
};

module_pci_driver(ob_driver);
MODULE_DESCRIPTION("OpenBook hardware check: PCI power management for functions without a driver (test only)");
MODULE_LICENSE("GPL");
