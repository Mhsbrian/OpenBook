| Where | Change before the cycle | S0i3 | HW sleep (us) | SMU | Idle mask at entry | Deepest C-state | Not in D3 at entry |
|---|---|---|---|---|---|---|---|
| OpenBook hwcheck-001.json | baseline | NO | 0 | Unknown/Fail | 0xffef9abd | None | 39 PCI functions, 17 not in D3 |
| OpenBook hwcheck-001.json | psp: 0000:65:00.2 1022:17e0 - -> openbook_pci_pm | NO | 0 | Unknown/Fail | 0xffef9afd | None | 41 PCI functions, 17 not in D3 |
| OpenBook hwcheck-001.json | dummy: 0000:66:00.0 1022:150d - -> openbook_pci_pm | NO | 0 | Unknown/Fail | 0xffef9afd | None | 41 PCI functions, 16 not in D3 |
| OpenBook hwcheck-001.json | asus: asus-wmi.ko loaded, asus-nb-wmi.ko not loaded, hid-asus.ko loaded | NO | 0 | Unknown/Fail | 0xffef9abf | None | 41 PCI functions, 16 not in D3 |

Verdict: {"openbook_reached_s0i3": false, "first_fixing_step": null, "linux_reached_s0i3": null, "linux_phases_without_s0i3": []}
