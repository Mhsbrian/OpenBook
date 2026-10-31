// SPDX-License-Identifier: GPL-2.0
/*
 * openbook_acpi_d3cold: test-only module for the OpenBook hardware check (ANAL-189). Never part of an image.
 *
 * When the PCI core sets up a bridge, acpi_dev_power_up_children_with_adr() powers the bridge's ACPI children with an
 * _ADR up to D0 so the bus behind it can be scanned. If nothing is found there, no PCI device ever becomes the
 * companion of that ACPI object, so nothing powers it down again: it stays D0 with its power resources referenced.
 * On the ASUS GA403WR this is \_SB.PCI0.GPP0.SWUS below the empty hotplug port 00:01.1, the only unmet LPI
 * constraint in its s2idle log, with \_SB.PCI0.GPP0.SWUS.PWRS left on.
 *
 * This module puts the named ACPI objects into D3cold through the normal ACPI PM path (_PS3, then the power
 * resources' _OFF once unreferenced), so one sleep test can show whether that is what keeps the SoC out of S0i3.
 * It refuses objects that are missing, not power-manageable, or the companion of a real device. Their parent's
 * device (the bridge) is held runtime-resumed during the change, because ACPI PM won't change a child while its
 * parent is in a deeper state. For this boot only; nothing persists.
 *
 * paths=: comma-separated ACPI paths; the leading backslash may be left out (kernel command lines).
 */
#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/acpi.h>
#include <linux/module.h>
#include <linux/pm_runtime.h>
#include <linux/slab.h>
#include <linux/string.h>

static char *paths = "_SB.PCI0.GPP0.SWUS";
module_param(paths, charp, 0444);
MODULE_PARM_DESC(paths, "comma-separated ACPI paths to put into D3cold (default _SB.PCI0.GPP0.SWUS)");

static const char *state_name(int state)
{
	static const char *const names[] = { "D0", "D1", "D2", "D3hot", "D3cold" };

	return state >= ACPI_STATE_D0 && state <= ACPI_STATE_D3_COLD ? names[state] : "unknown";
}

static void to_d3cold(const char *name)
{
	char path[128];
	acpi_handle handle;
	struct acpi_device *adev, *parent;
	struct device *phys, *bridge = NULL;
	int before, ret;

	snprintf(path, sizeof(path), "%s%s", name[0] == '\\' ? "" : "\\", name);
	if (ACPI_FAILURE(acpi_get_handle(NULL, path, &handle))) {
		pr_info("%s: not in the namespace\n", path);
		return;
	}
	adev = acpi_fetch_acpi_dev(handle);
	if (!adev) {
		pr_info("%s: no ACPI device object (not present)\n", path);
		return;
	}
	phys = acpi_get_first_physical_node(adev);
	if (phys) {
		pr_info("%s: companion of %s, left alone\n", path, dev_name(phys));
		return;
	}
	if (!adev->flags.power_manageable) {
		pr_info("%s: not power-manageable\n", path);
		return;
	}
	parent = acpi_dev_parent(adev);
	if (parent)
		bridge = acpi_get_first_physical_node(parent);
	if (bridge)
		pm_runtime_get_sync(bridge);
	before = adev->power.state;
	ret = acpi_device_set_power(adev, ACPI_STATE_D3_COLD);
	pr_info("%s: %s -> %s (%d)%s%s\n", path, state_name(before), state_name(adev->power.state), ret,
		bridge ? ", parent held on: " : "", bridge ? dev_name(bridge) : "");
	if (bridge)
		pm_runtime_put(bridge);
}

static int __init openbook_acpi_d3cold_init(void)
{
	char *list = kstrdup(paths, GFP_KERNEL), *cur = list, *name;

	if (!list)
		return -ENOMEM;
	while ((name = strsep(&cur, ",")))
		if (*name)
			to_d3cold(name);
	kfree(list);
	return 0;
}

static void __exit openbook_acpi_d3cold_exit(void)
{
}

module_init(openbook_acpi_d3cold_init);
module_exit(openbook_acpi_d3cold_exit);
MODULE_DESCRIPTION("OpenBook hardware check: put unused ACPI device objects into D3cold (test only)");
MODULE_LICENSE("GPL");
