// SPDX-License-Identifier: GPL-2.0
/*
 * Keep a closed laptop dark across suspend-to-idle resumes (ANAL-235).
 *
 * 1. drivers/acpi/button.c reports KEY_WAKEUP from every ACPI power button on
 *    every resume. Android treats KEYCODE_WAKEUP as a wake key, so any wake
 *    (EC, GPIO, USB) lights the panel even with the lid shut. Drop that
 *    KEY_WAKEUP while a lid switch reports closed, or if the lid was closed
 *    when the system suspended (the resume can briefly report a false open).
 *    Opening the lid still wakes Android through its own SW_LID event; a
 *    power-button press with the lid shut stays dark.
 *
 * 2. Shortly after a resume the firmware's _LID can report "open" with the lid
 *    shut (G14 GA403: _LID returns open whenever the EC is not marked ready).
 *    After each resume, re-read _LID a few times; if the switch reports open
 *    but _LID now says closed, report closed so the system can sleep again.
 *
 * Nothing is changed while the lid is open. Counters are module parameters.
 */
#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/acpi.h>
#include <linux/input.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/rcupdate.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/suspend.h>
#include <linux/workqueue.h>

#define MAX_LIDS 2

static bool drop_wakeup = true;
module_param(drop_wakeup, bool, 0444);
MODULE_PARM_DESC(drop_wakeup, "Drop resume KEY_WAKEUP from ACPI power buttons while a lid is closed");

static bool recheck_lid = true;
module_param(recheck_lid, bool, 0444);
MODULE_PARM_DESC(recheck_lid, "Re-read _LID after resume and correct a false open report");

static unsigned int dropped_wakeups;
module_param(dropped_wakeups, uint, 0444);
static unsigned int lid_corrections;
module_param(lid_corrections, uint, 0444);

static bool closed_at_suspend;
static DEFINE_MUTEX(lids_lock);
static struct input_handle *lids[MAX_LIDS];

/* Re-check delays after resume, in milliseconds. */
static const unsigned int recheck_ms[] = { 1000, 2500, 5000 };
static unsigned int recheck_step;
static struct delayed_work recheck_work;

static bool any_lid_closed(void)
{
	bool closed = false;
	int i;

	/* Lockless read of switch bits: a stale answer only delays one event. */
	for (i = 0; i < MAX_LIDS; i++) {
		struct input_handle *h = READ_ONCE(lids[i]);

		if (h && test_bit(SW_LID, h->dev->sw))
			closed = true;
	}
	return closed;
}

static bool is_acpi_power_button(struct input_dev *dev)
{
	return dev->phys && (str_has_prefix(dev->phys, "PNP0C0C/") ||
			     str_has_prefix(dev->phys, "LNXPWRBN/"));
}

static bool guard_filter(struct input_handle *handle, unsigned int type,
			 unsigned int code, int value)
{
	if (handle->private || type != EV_KEY || code != KEY_WAKEUP || !drop_wakeup)
		return false;
	if (!any_lid_closed() && !READ_ONCE(closed_at_suspend))
		return false;
	if (value)
		pr_info("lid closed: dropped resume KEY_WAKEUP from %s\n", handle->dev->name);
	dropped_wakeups++;
	return true;
}

static acpi_handle lid_acpi_handle(struct input_dev *dev)
{
	/*
	 * drivers/acpi/button.c names its lid "PNP0C0D/button/input0" and parents
	 * the input device on the acpi_device itself, whose dev.fwnode is unset,
	 * so ACPI_HANDLE() would return NULL. Other lid switches are left alone.
	 */
	if (!dev->phys || !str_has_prefix(dev->phys, "PNP0C0D/") || !dev->dev.parent)
		return NULL;
	return to_acpi_device(dev->dev.parent)->handle;
}

static void recheck_fn(struct work_struct *work)
{
	int i;

	mutex_lock(&lids_lock);
	for (i = 0; i < MAX_LIDS; i++) {
		struct input_handle *h = lids[i];
		unsigned long long lid;
		acpi_handle ah;

		if (!h || test_bit(SW_LID, h->dev->sw))
			continue; /* none, or already reported closed */
		ah = lid_acpi_handle(h->dev);
		if (!ah || ACPI_FAILURE(acpi_evaluate_integer(ah, "_LID", NULL, &lid)))
			continue;
		if (lid)
			continue; /* firmware agrees the lid is open */
		pr_info("%s reports open but _LID says closed %u ms after resume; reporting closed\n",
			h->dev->name, recheck_ms[recheck_step]);
		input_event(h->dev, EV_SW, SW_LID, 1);
		input_sync(h->dev);
		lid_corrections++;
	}
	mutex_unlock(&lids_lock);

	if (++recheck_step < ARRAY_SIZE(recheck_ms))
		schedule_delayed_work(&recheck_work,
				      msecs_to_jiffies(recheck_ms[recheck_step] - recheck_ms[recheck_step - 1]));
}

static int guard_pm_notify(struct notifier_block *nb, unsigned long action, void *data)
{
	if (action == PM_SUSPEND_PREPARE)
		WRITE_ONCE(closed_at_suspend, any_lid_closed());
	/* The resume KEY_WAKEUP is reported during device resume, before this. */
	if (action == PM_POST_SUSPEND)
		WRITE_ONCE(closed_at_suspend, false);
	if (action == PM_POST_SUSPEND && recheck_lid) {
		cancel_delayed_work(&recheck_work);
		recheck_step = 0;
		schedule_delayed_work(&recheck_work, msecs_to_jiffies(recheck_ms[0]));
	}
	return NOTIFY_DONE;
}

static struct notifier_block guard_pm_nb = {
	.notifier_call = guard_pm_notify,
};

static int guard_connect(struct input_handler *handler, struct input_dev *dev,
			 const struct input_device_id *id)
{
	bool lid = test_bit(EV_SW, dev->evbit) && test_bit(SW_LID, dev->swbit);
	bool power = test_bit(EV_KEY, dev->evbit) && test_bit(KEY_WAKEUP, dev->keybit) &&
		     is_acpi_power_button(dev);
	struct input_handle *handle;
	int err, i;

	if (!lid && !power)
		return -ENODEV;

	handle = kzalloc(sizeof(*handle), GFP_KERNEL);
	if (!handle)
		return -ENOMEM;
	handle->dev = dev;
	handle->handler = handler;
	handle->name = "openbook_lid_guard";
	/* private: NULL filters power-button keys; non-NULL marks a lid handle. */
	handle->private = power ? NULL : handle;

	err = input_register_handle(handle);
	if (err)
		goto free;
	err = input_open_device(handle);
	if (err)
		goto unregister;

	if (lid) {
		mutex_lock(&lids_lock);
		for (i = 0; i < MAX_LIDS && lids[i]; i++)
			;
		if (i < MAX_LIDS)
			WRITE_ONCE(lids[i], handle);
		mutex_unlock(&lids_lock);
	}
	pr_info("watching %s (%s)\n", dev->name, lid ? "lid" : "power button");
	return 0;

unregister:
	input_unregister_handle(handle);
free:
	kfree(handle);
	return err;
}

static void guard_disconnect(struct input_handle *handle)
{
	int i;

	mutex_lock(&lids_lock);
	for (i = 0; i < MAX_LIDS; i++)
		if (lids[i] == handle)
			WRITE_ONCE(lids[i], NULL);
	mutex_unlock(&lids_lock);
	synchronize_rcu(); /* filters read lids[] inside input core's RCU section */
	input_close_device(handle);
	input_unregister_handle(handle);
	kfree(handle);
}

static const struct input_device_id guard_ids[] = {
	{
		.flags = INPUT_DEVICE_ID_MATCH_EVBIT | INPUT_DEVICE_ID_MATCH_SWBIT,
		.evbit = { BIT_MASK(EV_SW) },
		.swbit = { [BIT_WORD(SW_LID)] = BIT_MASK(SW_LID) },
	},
	{
		.flags = INPUT_DEVICE_ID_MATCH_EVBIT | INPUT_DEVICE_ID_MATCH_KEYBIT,
		.evbit = { BIT_MASK(EV_KEY) },
		.keybit = { [BIT_WORD(KEY_WAKEUP)] = BIT_MASK(KEY_WAKEUP) },
	},
	{ }
};
MODULE_DEVICE_TABLE(input, guard_ids);

static struct input_handler guard_handler = {
	.filter = guard_filter,
	.connect = guard_connect,
	.disconnect = guard_disconnect,
	.name = "openbook_lid_guard",
	.id_table = guard_ids,
};

static int __init guard_init(void)
{
	int err;

	INIT_DELAYED_WORK(&recheck_work, recheck_fn);
	err = register_pm_notifier(&guard_pm_nb);
	if (err)
		return err;
	err = input_register_handler(&guard_handler);
	if (err)
		unregister_pm_notifier(&guard_pm_nb);
	return err;
}

static void __exit guard_exit(void)
{
	unregister_pm_notifier(&guard_pm_nb);
	cancel_delayed_work_sync(&recheck_work);
	input_unregister_handler(&guard_handler);
}

module_init(guard_init);
module_exit(guard_exit);
MODULE_DESCRIPTION("OpenBook: keep a closed laptop dark across s2idle resumes");
MODULE_LICENSE("GPL");
