| Where | Change before the cycle | S0i3 | HW sleep (us) | SMU | Idle mask at entry | Deepest C-state | Not in D3 at entry |
|---|---|---|---|---|---|---|---|
| OpenBook hwcheck-003.json | baseline | NO | None | None | None | None | - |
| OpenBook hwcheck-004.json | baseline | NO | None | None | None | None | - |
| OpenBook hwcheck-005.json | baseline | NO | None | None | 0xffef9afd | None | - |
| OpenBook hwcheck-006.json | baseline | NO | None | None | 0xffef9afd | None | - |
| OpenBook hwcheck-007.json | baseline | NO | None | None | 0xffef9afd | None | - |

Verdict: {"openbook_reached_s0i3": false, "first_fixing_step": null, "linux_reached_s0i3": null, "linux_phases_without_s0i3": []}
