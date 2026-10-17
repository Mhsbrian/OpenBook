/*
 * VM fixture for the power check (ANAL-178), loaded through the kernel's ACPI table upgrade (an uncompressed cpio
 * holding kernel/firmware/acpi/LPS0TEST.aml as the first initrd). QEMU's q35 firmware has no LPS0 device, so Linux
 * never calls the s2idle LPS0 hooks there and openbook_s0i3_snapshot cannot register. This adds a minimal one, like
 * the GA403WR's \_SB.PEP (SSDT "UPEP"): _CID PNP0D80, and a _DSM that answers the Microsoft LPS0 UUID with the
 * same function mask the laptop reports (0x1F9: screen off/on, entry/exit, Modern Standby entry/exit) and does
 * nothing else. No constraints list (the AMD UUID is not implemented).
 * Test copies only; never on a stick for a laptop.
 */
DefinitionBlock ("", "SSDT", 2, "OPENBK", "LPS0TEST", 1)
{
    Scope (\_SB)
    {
        Device (PEPT)
        {
            Name (_HID, "OBLP0001")
            Name (_CID, EisaId ("PNP0D80"))
            Name (_UID, One)
            Name (CNT, Zero)    /* _DSM calls, for a debugger */
            Method (_STA, 0, NotSerialized)
            {
                Return (0x0F)
            }

            Method (_DSM, 4, Serialized)
            {
                CNT++
                If ((Arg0 == ToUUID ("11e00d56-ce64-47ce-837b-1f898f9aa461")))
                {
                    If ((ToInteger (Arg2) == Zero))
                    {
                        Return (Buffer (0x02) { 0xF9, 0x01 })
                    }
                    Return (Zero)
                }
                Return (Buffer (One) { 0x00 })
            }
        }
    }
}
