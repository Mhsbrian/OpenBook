# microG add-on in QEMU (ANAL-210): 56/62

| Case | Check | Result |
|---|---|---|
| addon-logs | every expect step matched | pass |
| addon-logs | the helper's capture has the ADDONS section | pass |
| addon-logs | ... with openbook-addons' state and microG's three packages | pass |
| addon-logs | ... and microG as the network provider, coordinates redacted | pass |
| plain | every expect step matched | pass |
| plain | SELinux enforcing | pass |
| plain | no denial for an OpenBook domain | FAIL: ['10-18 01:39:01.252  3150  3150 I auditd  : type=1400 audit(0.0:6): avc:  denied  { write } for  comm="openbook-addons" path="/dev/kmsg_debug" dev="t |
| plain | openbook-addons ran and found no add-on | pass |
| plain | the wizard's disk screen has no add-on switch | FAIL: <node text="" checkable="true" checked="true" drawing-order="3" hint=""
<node text="" checkable="true" checked="false" drawing-order="0" hint=""
<node |
| plain | no microG package | pass |
| main | every expect step matched | pass |
| main | SELinux enforcing | pass |
| main | no denial for an OpenBook domain | pass |
| addon | every expect step matched | pass |
| addon | SELinux enforcing | pass |
| addon | no denial for an OpenBook domain | FAIL: ['10-18 01:41:11.512  3214  3214 I auditd  : type=1400 audit(0.0:6): avc:  denied  { write } for  comm="openbook-addons" path="/dev/kmsg_debug" dev="t |
| addon | openbook-addons installed the add-on | pass |
| addon | the three packages at the pinned versions | pass |
| addon | installed in /data as normal apps | pass |
| addon | GmsCore holds ACCESS_FINE_LOCATION | pass |
| addon | GmsCore holds ACCESS_BACKGROUND_LOCATION | pass |
| addon | GmsCore holds POST_NOTIFICATIONS | pass |
| addon | GmsCore holds RECEIVE_SMS | pass |
| addon | GmsCore holds INTERACT_ACROSS_USERS | pass |
| addon | SYSTEM_ALERT_WINDOW allowed | pass |
| addon | battery-optimisation exemption | pass |
| addon | microG Services has a launcher entry | pass |
| addon | microG self-check: all green (17/17) | pass |
| addon | init started openbook_addons after boot_completed | pass |
| addon-2 | every expect step matched | pass |
| addon-2 | SELinux enforcing | pass |
| addon-2 | no denial for an OpenBook domain | FAIL: ['10-18 01:42:38.700  1440  1440 I auditd  : type=1400 audit(0.0:4): avc:  denied  { write } for  comm="openbook-addons" path="/dev/kmsg_debug" dev="t |
| addon-2 | second boot: nothing reinstalled (already installed) | pass |
| addon-2 | microG is the network location provider (installed in /data) | pass |
| addon-2 | microG is the fused location provider | pass |
| install | every expect step matched | pass |
| install | SELinux enforcing | pass |
| install | no denial for an OpenBook domain | FAIL: ['10-18 01:56:13.016  1499  1499 I auditd  : type=1400 audit(0.0:6): avc:  denied  { write } for  comm="openbook-addons" path="/dev/kmsg_debug" dev="t |
| install | the wizard's disk screen shows the microG switch, off | pass |
| install | tapping it turns it on | pass |
| install | "View the plan" then lists the add-on check | pass |
| install | the stick carries the add-on (openbook-install addons) | pass |
| install | the plan names the add-on and checks it | pass |
| install | install ok and verified | pass |
| installed | every expect step matched | pass |
| installed | SELinux enforcing | pass |
| installed | no denial for an OpenBook domain | FAIL: ['10-18 02:00:06.016  3081  3081 I auditd  : type=1400 audit(0.0:6): avc:  denied  { write } for  comm="openbook-addons" path="/dev/kmsg_debug" dev="t |
| installed | openbook-addons installed the add-on | pass |
| installed | the three packages at the pinned versions | pass |
| installed | installed in /data as normal apps | pass |
| installed | GmsCore holds ACCESS_FINE_LOCATION | pass |
| installed | GmsCore holds ACCESS_BACKGROUND_LOCATION | pass |
| installed | GmsCore holds POST_NOTIFICATIONS | pass |
| installed | GmsCore holds RECEIVE_SMS | pass |
| installed | GmsCore holds INTERACT_ACROSS_USERS | pass |
| installed | SYSTEM_ALERT_WINDOW allowed | pass |
| installed | battery-optimisation exemption | pass |
| installed | microG Services has a launcher entry | pass |
| installed | microG self-check: all green (18/18) | pass |
| installed | init started openbook_addons after boot_completed | pass |
| plain | the same packages as the image from main | pass |
| addon | exactly microG's three packages more than without the add-on | pass |
