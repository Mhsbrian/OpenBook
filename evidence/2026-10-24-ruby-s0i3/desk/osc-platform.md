# Platform-wide `_OSC` on the G14 (ANAL-257)

**What each kernel offers** (`drivers/acpi/bus.c`, `acpi_bus_osc_negotiate_platform_control()`; bit values from
`include/linux/acpi.h`, identical in 6.18 and 7.2):

| Bit | Name | GKI vmlinux (6.18.21) | Linux 7.2.8 |
|---|---|---|---|
| 0x1 | PAD (`ACPI_PROCESSOR_AGGREGATOR`) | no | yes |
| 0x2 | PPC _OST | yes | yes |
| 0x4 | _PR3 | yes | yes |
| 0x8 | hotplug _OST | yes | yes |
| 0x10 | APEI (`ghes_disable` is 1 without `ACPI_APEI`) | no | yes |
| 0x20, 0x40 | CPC, CPPC v2 | yes | yes |
| 0x80 | PC LPI | yes | yes |
| 0x200 | fast thermal sampling (`ACPI_THERMAL` built in) | no | yes |
| 0x400, 0x800, 0x1000, 0x2000, 0x4000 | >16 P-states, GED, diverse high, IRQ ResourceSource, CPC flexible | yes | yes |
| 0x20000 | generic initiator | yes | yes |
| 0x40000 | native USB4 (`IS_ENABLED(CONFIG_USB4)`, a module on both) | yes | yes |
| 0x80000 | battery charge limiting (`ACPI_BATTERY` built in) | no | yes |
| 0x200000 | PRM | yes | yes |
| 0x400000 | FFH opregion | no | yes |
| | **mask** | **`0x00267cee`** (computed from the config) | **`0x006e7eff`** (logged: `\_SB_: platform _OSC: OS support mask [006e7eff]`) |

6.18 does not log the mask; 7.2 added the log line, so its absence from our logs is not a missing call.

**What the firmware does with it** (SSDT "CPMMSOSC", `\_SB._OSC`, platform UUID `0811b06e-…`): sets bit 2 (_PR3)
in its answer, clears bit 7 (PC LPI, `MSDB`), keeps or drops bit 18 (USB4) by its own settings (`U4PC`), clears the
USB4 `_DEP` flag (`DDEP`) when the OS offers bit 18, and on the non-query call sends `M625(0x0102 + …)`. None of the
bits that differ (PAD, APEI, fast thermal sampling, battery charge limiting, FFH) is read. Both kernels offer bit 18
and make both calls, so the firmware sees the same thing. **Ruled out** (CONFIRMED from the table).

The PCI host bridge `_OSC` gives the same control on both (`OS now controls [PCIeHotplug PME PCIeCapability]`;
`platform does not support [AER LTR]`, plus `SHPCHotplug DPC` on 7.2, which asks for more).
