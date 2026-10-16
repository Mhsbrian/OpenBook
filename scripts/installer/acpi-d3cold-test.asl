/*
 * VM fixture for openbook_acpi_d3cold (ANAL-189), loaded through the kernel's ACPI table upgrade (an uncompressed cpio
 * holding kernel/firmware/acpi/NAME.aml as the first initrd). It mirrors the GA403WR's \_SB.PCI0.GPP0.SWUS: an _ADR child
 * with its own power resource below a PCIe root port. Here the port is QEMU's S20_ (00:04.0, qemu-run.py
 * --detach-test-device); once the probe removes the device behind it, TSWU is an ACPI object that no device uses.
 * The power resource's state is visible in sysfs (resource_in_use, real_power_state), which the probe records.
 */
DefinitionBlock ("", "SSDT", 2, "OPENBK", "D3TEST", 1)
{
    External (\_SB.PCI0.S20_, DeviceObj)

    Scope (\_SB.PCI0.S20_)
    {
        Device (TSWU)
        {
            Name (_ADR, Zero)
            PowerResource (PWRS, 0, 0)
            {
                Name (STAT, One)
                Method (_STA, 0, NotSerialized) { Return (STAT) }
                Method (_ON, 0, NotSerialized) { STAT = One }
                Method (_OFF, 0, NotSerialized) { STAT = Zero }
            }
            Name (_PR0, Package (One) { PWRS })
            Name (_PR3, Package (One) { PWRS })
        }
    }
}
