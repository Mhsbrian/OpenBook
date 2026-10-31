/*
 * Test-only ACPI lid for the openbook_lid_guard VM test (ANAL-235). The lid is
 * physically "closed", but _LID reports open for 0.5 s after each S3 resume,
 * like the G14's _LID right after a wake. Loaded with QEMU -acpitable only.
 */
DefinitionBlock ("", "SSDT", 2, "OPNBK", "LIDTEST", 0x00000001)
{
    Name (WAKT, Zero)
    Method (\_WAK, 1, NotSerialized)
    {
        WAKT = Timer
        Return (Package (0x02) { Zero, Zero })
    }

    Scope (\_SB)
    {
        Device (LID0)
        {
            Name (_HID, EisaId ("PNP0C0D"))
            Method (_LID, 0, NotSerialized)
            {
                If (WAKT == Zero)
                {
                    Return (Zero)
                }
                If ((Timer - WAKT) < 5000000)
                {
                    Return (One)
                }
                Return (Zero)
            }
        }
    }
}
