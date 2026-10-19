# Quire: the agent layer of OpenBook (ANAL-214)

As of 2026-10-18. Labels: **C** = confirmed (we read it in a primary source or in our AOSP 17 tree, or ran it ourselves), **R** = reported (press or third party), **HYPOTHESIS** = not yet tested. Evidence for what is built is in [`evidence/2026-10-18-quire/`](../evidence/2026-10-18-quire/) (Q1), [`evidence/2026-10-18-quire-q2/`](../evidence/2026-10-18-quire-q2/) (Q2) and [`evidence/2026-10-18-quire-q4/`](../evidence/2026-10-18-quire-q4/) (Q4).

## Summary

- **Quire connects OpenBook to the AI agents a person already has.** That includes Claude Code, Codex, Copilot, Cursor, Gemini CLI, Grok, opencode and Kimi, and any agent that speaks the open Agent Client Protocol. A person calls it from anywhere: shake the pointer, press a key, hold the mic key and talk. A note flies out from the pointer, the agent works in it in plain sight, and the note folds away when the work is done. The agent can drive the system: change a setting, open an app, carry out a task in an app. The design requires that it does so only with the person's consent, on a separate display they can watch, and that they can take control at any moment. Q1 does not enforce that yet; §5 says what it does enforce.
- **Googlebook's announced agent features run on Gemini, with Google's closed apps** (Magic Pointer, Create your Widget). Google's post does not say whether other agents can be used (unverified). Quire does any agent, in the open. **AOSP 17 contains platform hooks that fit those features**, under Apache-2.0: the pointer-shake gesture, contextual search, the assistant role and **computer control**, a framework API that lets an agent operate apps on a virtual display with consent and hand-over (§2). Whether Googlebook's shipping image uses these exact hooks is unverified. Quire plugs into them rather than hacking around them.
- **Two open protocols, no lock-in.** Agents talk to Quire over **ACP** (Agent Client Protocol, Apache-2.0, v1), the protocol Zed and others use for editors. Quire gives its OS tools to agents over **MCP** (Model Context Protocol). An agent that speaks ACP works with Quire with no Quire-specific code. For agents that don't, `quired` adapts them.
- **Built today: `quired`, the harness host for trusted local agents.** It finds the agent CLIs on a machine, runs them, and gives every one of them the same ACP interface. On this host it opened real ACP sessions with opencode, Copilot and omp. Through its Claude Code adapter it ran real turns in which the person's "allow" or "deny" decided whether a file was written. It has 22 unit tests that pass with the race detector, including regressions for the faults the ANAL-217 review found (§6).
- **Built in Q2: Quire core in the image, and the AOSP 17 hooks working** (§2.5, §2.6). In Cuttlefish, a pointer shake, Meta+Space and the assist key each open Quire with a screenshot that leaves secure windows out and the list of visible apps. Quire asks for a computer-control session on Settings; the platform's own consent dialog appears; Settings runs on a separate display that Quire mirrors; a tap through the session turns Dark theme on; "take over" moves Settings to the person's screen. A denied consent, the lock screen and a secure window each stop it. Getting there took four small AOSP patches, all fixes or device configuration rather than relaxed checks.
- **Built in Q4: agents run on the laptop itself** (§4.1). Both images carry AVF and its Terminal app. The Debian guest is built here, with `quired` in it, and Quire core reaches that `quired` over vsock through a bridge in the Terminal app. In Cuttlefish, under nested KVM on AMD, the guest boots in about 12 s. `quired agents` in its terminal lists opencode, installed there, and a prompt sent from Quire core comes back from opencode in the guest. Without KVM, Quire says the Linux environment can't run and names a paired computer as the fallback. Pairing is designed and under review ([`docs/quire-pairing.md`](quire-pairing.md)); it is not built. The G14 run waits for the owner's stick.
- **How we learned from Multica (reviewed, not copied).** Multica's daemon detects agent CLIs and drives each through its own output format. Its licence adds conditions on commercial embedding. Quire takes the idea of detecting and running the agents a person has, and builds it on open protocols with its own code. No Multica code is used (§3).

## 1. The experience

What a person sees. Atelier owns the visual and motion design (ANAL-215); this is the brief.

1. **Call it.** From anywhere, by any of:
   - shaking the pointer (AOSP 17's own contextual-cursor gesture, §2.2);
   - a key (Meta+Space, and the keyboard's assistant or Copilot key if it has one);
   - the Quire button on the taskbar;
   - holding the mic key, or a hold-to-talk key, and speaking;
   - selecting text or an image and choosing "Ask Quire".

   Quire takes in what is under the pointer: the screenshot region, the selected text, the app's name. It never reads a window marked secure.
2. **The note.** A card grows out of the pointer, not out of a corner, and settles beside it. It shows which agent is answering ("Claude Code · on this laptop"). The answer streams in. Each step the agent takes shows as a line that ticks: "Reading Wi-Fi settings ✓", "Turning on Battery saver…".
3. **Consent, inline.** When the agent wants to change something, the step stops and offers **Allow**, **Allow for this task** and **Don't allow**. The step names exactly what will change. Nothing that changes the system happens without this, unless the person has given standing permission for that tool.
4. **Driving the system.** When the agent needs to operate an app, the app runs on a separate virtual display (computer control, §2.4). The note expands into a live mirror of that display, with the agent's pointer and highlights drawn on it. The person can watch, pause, or press **Take over**, which moves the app onto their own screen. Apps being automated show an indicator in the taskbar. AOSP 17 has `enable_app_automation_indicator` for this.
5. **Done.** The note shows the result and folds back into the pointer, or into the taskbar button if the work is still running. Finished and running tasks live behind the taskbar button.
6. **Settings help.** "Make my screen easier to read at night" → Quire shows the two or three settings it would change, with their current and new values, then applies them on Allow. It can always undo: every change Quire makes is listed with an undo.

Motion principles for the brief: the note is anchored to where the person's attention already is; it moves with spring physics, not linear easing; it respects "Remove animations"; and everything in it is reachable by keyboard and screen reader.

## 2. What Googlebook does, and what AOSP 17 already provides

### 2.1 Googlebook (R, except where marked)

- **Magic Pointer** (built with Google DeepMind): "Just wiggle your cursor and watch it come alive with Gemini". It offers help based on what the pointer is over, for example turning a date in an email into a meeting. Source: Google, "Introducing Googlebook", 2026-05-12.
- **Create your Widget:** Gemini builds a desktop dashboard from a prompt, and can draw on the web, Gmail and Calendar. Same source.
- **Rambler:** cleaned-up dictation (R, secondary report of a Google post, 2026-09-21).
- **On the image (C, `docs/googlebook-ui.md` §2):**
  - gPointer (Magic Pointer, 224 MB);
  - Desktop System Intelligence (`alai`);
  - Gemini and the Gemini shell;
  - the Glowbar.

  All of them are proprietary and signed with Google's keys, so **none can ship on OpenBook**, and Quire does not imitate their branding.

### 2.2 The pointer-shake gesture (C)

`frameworks/base/packages/SystemUI/src/com/android/systemui/contextualcursor/`:

- `GestureDetectionInteractor` detects a shake from cursor positions, with a range threshold in dp and a cooldown.
- `ContextualCursorInteractor` listens only once the user is set up, provisioned and past the lock screen. On a shake it calls `LauncherProxy.invokeContextualSearch(ENTRYPOINT_SYSTEM_ACTION)`.
- The code carries a TODO: it "temporarily invoke[s] contextual search before the actual launch method is landed".
- The flag is `com.android.hardware.input.enable_contextual_cursor_desktop_entrypoints`. ANAL-204 skipped it as an "AI service OpenBook does not have"; Q2 turns it on (`release/openbook/`).
- **Keys, as Q2 found them (C):**
  - **Meta+G** is the contextual cursor's shortcut (same flag). SystemUI maps it to contextual search too, for now (TODO b/484184229).
  - **Meta+A** is the contextual search shortcut (`enable_contextual_search_desktop_entrypoints`, already enabled in cp2a).
  - **Meta+Space is not contextual search:** `InputGestureManager` maps it to `KEY_GESTURE_TYPE_LAUNCH_ASSISTANT`, like the Copilot key's sequence and the assist key. All three go to the assistant role holder, so they reach Quire through its `VoiceInteractionService` (§2.3).
- **The shake detector reads an `InputMonitor`** and only takes `SOURCE_MOUSE` or `SOURCE_TOUCHPAD` events: at least 3 left-right direction changes within 500 ms, inside a 100 dp box, then a 3 s cooldown. A shake goes SystemUI → `LauncherProxy.invokeContextualSearch(ENTRYPOINT_SYSTEM_ACTION)` → Launcher3's `ContextualSearchInvoker`.

### 2.3 Contextual search and the assistant role (C)

- `ContextualSearchManager` starts the activity of the package named in `config_defaultContextualSearchPackageName` with `ACTION_LAUNCH_CONTEXTUAL_SEARCH`. It passes:
  - `EXTRA_SCREENSHOT`;
  - `EXTRA_VISIBLE_PACKAGE_NAMES`;
  - `EXTRA_FLAG_SECURE_FOUND`;
  - `EXTRA_IS_AUDIO_PLAYING`;
  - `EXTRA_ENTRYPOINT`;
  - a token.

  The overlay value is empty in AOSP. Setting it to Quire is necessary but not enough: the package needs an activity that resolves `ACTION_LAUNCH_CONTEXTUAL_SEARCH` (`ContextualSearchManagerService.getResolvedLaunchIntent`), and the extras are conditional. The screenshot comes only when the capture worked and assist data is allowed, and the audio extra only with `Flags.includeAudioPlayingStatus()`.
- **What else contextual search needs (C, Q2):**
  - Launcher3 refuses to invoke it unless the device declares the feature `com.google.android.feature.CONTEXTUAL_SEARCH` (`ContextualSearchManager.FEATURE_CONTEXTUAL_SEARCH`; AOSP's own name) and its activity resolves for Launcher3. Quire's image declares the feature, and its activity is exported but protected by `ACCESS_CONTEXTUAL_SEARCH`.
  - On a `FEATURE_PC` device the service returns no package unless `enable_contextual_search_desktop_entrypoints` is on. It is, in cp2a.
  - The screenshot leaves out `FLAG_SECURE` layers and reports them (`EXTRA_FLAG_SECURE_FOUND`). Screenshot and visible packages are withheld when assist data is not allowed.
  - **The service also hands the app a `MediaProjection`** (`EXTRA_MEDIA_PROJECTION`, created for the contextual search package). Quire never uses it.
- **The assist key and Meta+Space reach Quire's assistant session, not contextual search.** Quire's session hands each one to contextual search itself (`ContextualSearchManager.startContextualSearch`, which needs `ACCESS_CONTEXTUAL_SEARCH`, signature|privileged). Every way of calling Quire therefore arrives the same way, with the same screenshot rules. Contextual search has no entry point for the assist key, so Quire passes `ENTRYPOINT_KEYBOARD_SHORTCUT` and adds its own `trigger` extra (`assist_key`, `assistant_shortcut`).
- The legacy route where a session asks the voice interaction service for contextual search (`showSessionFromSession` with `config_defaultContextualSearchKey`) is disabled in `trunk_staging` (`disable_starting_contextual_search_via_vims`), so Quire doesn't use it.
- Holding the assistant role makes the assistant's recognition service the system's speech recognizer. Quire's says "not available" until Q7.
- The assistant role (`ROLE_ASSISTANT`, a `VoiceInteractionService`) gives the assist key, long-press gestures and voice. Computer control requires the agent to hold it (`computer_control_role_assistant_requirement`, enabled in cp2a).

### 2.4 Computer control (C)

`android.companion.virtual.computercontrol` in AOSP 17 (`ComputerControlSession`, `ComputerControlSessionParams`, `InteractiveMirror`, `ComputerControlConsentManager`; service side in `services/companion/.../computercontrol/`):

- A **session** is a trusted virtual display with input devices. The agent can:
  - launch the apps it was granted (`setTargetPackageNames`);
  - inject taps and input;
  - take screenshots (`requestScreenshot`);
  - go back.
- **Safety is built in:**
  - the session blocks on secure content (`BLOCK_REASON_SECURE_CONTENT`), on disallowed activity launches and on biometric prompts;
  - the user can close it or take over;
  - `handOverApplications()` moves the automated apps to the user's display;
  - sessions time out.
- `InteractiveMirror` gives the controlling app a surface mirroring the session display, which can be made interactive. That is the live view in §1.4.
- **Consent:**
  - `RequestComputerControlAccessActivity` in `frameworks/base/packages/VirtualDeviceManager` asks the user;
  - per-app consent, where the person approves each target app for each agent (`MANAGE_COMPUTER_CONTROL_CONSENT`, signature), exists only behind `computer_control_per_app_consent`, which is enabled in `trunk_staging` and **not in cp2a**;
  - a notification shows while automation runs.
- **Who may create a session** (`ComputerControlAllowlistController.isPackageAllowedToCreateSession`, frameworks/base `8f5dedd3edc3`):
  - `ACCESS_COMPUTER_CONTROL` (`internal|privileged`) and `POST_NOTIFICATIONS`;
  - the assistant role, while `_role_assistant_requirement` is on;
  - an entry in the session-owner allowlist that matches the package name **and its signing certificate** (`session_owner_allowlist.txt`, or the `allowed_session_owner_apps` DeviceConfig key).

  OpenBook builds its own image, so Quire can be a privileged system app with that allowlist entry. Debuggable builds also have a "super agent" list that skips all of these checks. A session that works that way is not evidence that the ordinary path is safe.
- **Flags:**
  - `computer_control_access`, `computer_control_support_v5` and `computer_control_per_app_consent` are **not enabled in cp2a**, our release config. They are enabled in `trunk_staging`. Q2 turns all three on (below).
  - `_role_assistant_requirement` and `_managed_profiles` are enabled in cp2a. cp2a also carries values for `computer_control_consent`, `_activity_policy_strict`, `_user_restriction` and `_config_change_override`, but **AOSP 17 declares none of those four** (no `.aconfig` entry, not in `aflags list`; checked in Q2), so the code they would gate is either unconditional (the consent dialog) or absent.
  - Launcher3's `enable_app_automation_indicator` is enabled.
  - **Q2 turns on `computer_control_access` and `computer_control_support_v5`** in OpenBook's own value set (`device/anybook/common/desktop/release/openbook/cp2a/`). It leaves `_per_app_consent`, `_typing`, `_cross_device` and `notification_flag_computer_control` off; they are in `trunk_staging` only (§8).
- **The API is `@hide`** (no `system-current.txt` entry). A platform app built in-tree, as Quire's core will be, can use it. Third-party apps can't. (AOSP also has a public extension library, `frameworks/base/libs/computercontrol`, `com.android.extensions.computercontrol`, with a ready `MirrorView`; Quire uses the framework API directly.)
- **What a session needs, as Q2 found it (C):**
  - **An allowlist entry.** `ComputerControlAllowlistController` lets a package own a session only if it is in DeviceConfig `computer_control/allowed_session_owner_apps` (package and signing-certificate SHA-256, upper-case hex), and lets it automate only apps in `allowed_automatable_apps` (`PREINSTALLED` matches the system image's copy; the permission controller and approved agents never match). The last valid DeviceConfig value is persisted in `/data/system/computercontrol/`. **A device without a configuration server has neither, so no agent can ever own a session.** OpenBook adds a third source, read only when both are empty: the image's own lists in `/system_ext/etc/computercontrol/` (`aosp/patches/frameworks/base/0005`). Nothing else changes: the permission, the role, the consent, the lock screen and the block reasons are checked as before. "Super agents" (`config_computerControlKnownSuperAgents`) bypass the allowlists on debuggable builds only; Quire doesn't use them.
  - **Version 5** (`computer_control_support_v5`): `VirtualDeviceManager.COMPUTER_CONTROL_VERSION` becomes 5. A version 5 request must carry a promotable notification (ongoing, titled, `setRequestPromotedOngoing`), which the platform posts for the agent and makes undismissable, and an `AppInteractionAttribution` (`enable_app_interaction_api` is on in cp2a). It may name at most six apps, and the agent must have a visible window.
  - **One session at a time** (`MAXIMUM_CONCURRENT_SESSIONS = 1`), each with a name unique to the agent; 60 minutes at most.
  - **Consent.** The app op `COMPUTER_CONTROL` defaults to `MODE_DEFAULT`, so every request without "Always allow" opens `RequestComputerControlAccessActivity`: "Only this time", "Always allow" (sets the op to allowed) or "Don't allow". Three denials in a row set the op to ignored, and later requests fail at once. Without `computer_control_per_app_consent` the consent is for the agent as a whole. **Q2 turns it on:** the dialog then names each app ("Allow Quire to use screen automation with Settings?"), "Always allow" covers that app only (the platform keeps the list in `/data/system_de/0/`), and any app the person has not approved asks again, by itself.
  - **The lock screen** is checked when the session is created (`ERROR_DEVICE_LOCKED`); the session display itself is always unlocked.
  - **`handOverApplications()`** moves the session's tasks to the main display and closes the session (`CLOSE_REASON_SESSION_EMPTY`).
  - The flag `computer_control_access` also turns on safety paths outside the session: a warning when the user launches an app that is being automated, the session notification's no-clear flags, and Settings' "Screen automation" special access page.

### 2.5 What OpenBook changes in AOSP 17 for Quire (Q2, ANAL-216)

The hooks exist, but four of them do not work on a device like OpenBook's out of the box (C, found in Cuttlefish).
Each change is the smallest that makes the hook work, and none relaxes a safety check:

| Change | Why |
|---|---|
| `aosp/patches/frameworks/base/0005`: computer control's allowlists fall back to `/system_ext/etc/computercontrol/` | The allowlists come only from DeviceConfig (server-pushed) or a persisted copy of it, so on a device with no configuration server no agent can ever own a session. The image's own list is read only when both are empty; DeviceConfig still wins. Unit tests added (not run: they need the VirtualDeviceServicesTests suite on a device) |
| `aosp/patches/frameworks/base/0006`: SystemUI arms the shake detector without a headless system user | It armed only when logout is enabled, which the system user never is. Googlebook runs in headless system user mode; OpenBook's person is user 0. SystemUI unit test updated (not run) |
| `aosp/patches/frameworks/base/0007`: `ComputerControlSession` creates its accessibility proxy before `initialize()` | AOSP registered the proxy before creating it (an NPE that Binder swallowed), so an agent could never read the apps it automates |
| `aosp/patches/packages/apps/Launcher3/0002` and a privapp entry: Launcher3 requests `ACCESS_CONTEXTUAL_SEARCH` | Launcher3 starts contextual search for the shake, Meta+A and Meta+G, and was denied every time |
| `RELEASE_PACKAGE_COMPUTER_CONTROL=true` (`device/anybook/common/desktop/release/flag_values/cp2a/`) | Installs VirtualDeviceManager, which holds the platform's consent dialog. Without it every request that needs consent fails |
| The flags `computer_control_access`, `computer_control_support_v5`, `computer_control_per_app_consent`, `enable_contextual_cursor_desktop_entrypoints` | §2.2, §2.4 |
| The feature `com.google.android.feature.CONTEXTUAL_SEARCH` | Launcher3 checks it (§2.3) |

### 2.6 Q2 in Cuttlefish: what held (C)

Cuttlefish on the AMD lane, `anybook_cf_x86_64_pc`, third Q2 image, with per-app consent on; evidence in
[`evidence/2026-10-18-quire-q2/`](../evidence/2026-10-18-quire-q2/) (`SUMMARY.md`). `scripts/quire/q2-cf-check.py`, one
run on a fresh device: 69 pass, 0 fail.

- **Invocation.** The pointer shake (a virtual USB mouse), Meta+Space and the assist key each open Quire's note. The
  shake arrives as `ENTRYPOINT_SYSTEM_ACTION` through SystemUI and Launcher3; the two keys arrive through Quire's
  assistant session as `ENTRYPOINT_KEYBOARD_SHORTCUT`, with Quire's trigger `assistant_shortcut` or `assist_key`. Each
  carries the visible packages (Settings, the secure test window's app, Launcher3), `EXTRA_FLAG_SECURE_FOUND=true`, and
  a 1920×1080 screenshot in which the secure window is black.
- **Computer control,** through the ordinary allowlist path (no debug super agent). A version 5 session for Settings:
  fresh consent in the platform's dialog ("Allow Quire to use screen automation with Settings?"), Settings' Dark theme
  page on the session display, Quire's mirror of it, the undismissable "Quire is
  using Settings" notification, two session screenshots, a tap found through the session's accessibility tree that
  turned Dark theme on, and `handOverApplications()` moving Settings to the main display and closing the session.
- **Refusals,** each from the platform: "Don't allow" → `ERROR_PERMISSION_DENIED`; the lock screen →
  `ERROR_DEVICE_LOCKED`; a secure window on the session display → `BLOCK_REASON_SECURE_CONTENT`, after which the
  platform refuses Quire's tap and the mirror goes black; an app outside the allowlist → `IllegalArgumentException`.
- **Per-app consent:** "Always allow" for Settings, and the next request for Settings needs no dialog; a request that
  adds a second, unapproved app asks again for that app alone, and "Don't allow" refuses the whole session.
- **No regression:** the desktop defaults check 16/16, the desktop capture as before, no crash, ANR or SystemUI restart
  in the whole session, and only the three SELinux denials Cuttlefish always has. Quire needed no SELinux policy: it
  runs as `platform_app`, and every service it uses is an `app_api_service`.
- **Not yet:** the G14 (no boot of this image on the laptop); the new unit tests in the patches (not run).

## 3. How Multica runs agents, and what Quire does instead

Reviewed from Multica's public README, its CLI's help, and its observable behaviour on this host (`multica` 0.6.3). We read none of Multica's source code and copied none.

| | Multica | Quire |
|---|---|---|
| Where agents run | A daemon on a computer the person owns. It detects agent CLIs on `PATH`; on this host it reports 11 runtimes | `quired` on the laptop's Linux environment (AVF Terminal), or on a computer the person pairs. It detects the same way: a catalog of known CLIs, resolved on `PATH` and asked for `--version` |
| How it talks to agents | Each provider's own headless mode and output format | **ACP** wherever the agent has it. Today that is opencode, Copilot, Cursor, Kimi, Hermes and omp, and Gemini CLI by its docs. Adapters exist only for agents without ACP: Claude Code today; Codex, Grok and Antigravity planned |
| What drives the work | Issues and comments on a server | The person, live: a gesture, a key or their voice, on their own laptop |
| Tools the agent gets | The `multica` CLI, through a task token | OpenBook's OS tools as an **MCP server** (settings, apps, windows, computer control), passed in ACP `session/new` |
| Permissions | The agent's own setting; Multica runs agents unattended | The agent asks when its own policy says to: ACP makes `session/request_permission` optional, and the note shows each request inline. For Claude Code, `quired` serves Claude's `--permission-prompt-tool` over MCP and forwards each question Claude's settings send it (§6). OS tools will be authorized by Quire core on every call, whatever the agent asks (§5.3) |
| Licence | Multica License: Apache-2.0 text plus extra conditions on hosted services, commercial embedding and branding | OpenBook's own code. ACP and its SDKs are Apache-2.0. We don't use Multica code, which also keeps the embedding conditions out of the picture |

## 4. Architecture

```mermaid
flowchart LR
  subgraph laptop["OpenBook (Android 17)"]
    surface["Quire surface<br/>note · mirror · consent<br/>(SystemUI / Launcher3 overlay)"]
    core["Quire core<br/>privileged system app<br/>sessions · policy · audit"]
    tools["OS tools (MCP)<br/>settings · apps · windows<br/>computer control"]
    hooks["AOSP 17 hooks<br/>shake gesture · contextual search<br/>assistant role · computer control"]
    hooks --> core
    surface <--> core
    core --- tools
    subgraph vm["Linux environment (AVF)"]
      quired["quired<br/>harness host"]
      agents["agent CLIs<br/>Claude Code · Codex · Gemini · …"]
      quired <-- "ACP (stdio)" --> agents
    end
    core <-- "ACP over vsock" --> quired
    agents -. "MCP tool calls" .-> tools
  end
  pc["a paired computer<br/>running quired"] <-. "ACP over an encrypted link (later)" .-> core
  cloud["cloud APIs with the person's key<br/>(no CLI needed)"] <-. "HTTPS" .-> core
```

- **Quire core** (`dev.openbook.quire`, built in-tree, privileged):
  - holds `ROLE_ASSISTANT` and is the contextual search package;
  - holds `ACCESS_COMPUTER_CONTROL`;
  - runs sessions and permission policy;
  - keeps the audit log of every change it made, with undo where possible.
  - It is an ACP **client**, so it can talk to any ACP agent anywhere.
- **Quire surface:** the note, the mirror and the inline consent, drawn above apps in SystemUI's or Launcher3's layer. Atelier designs it (ANAL-215).
- **OS tools** (not built, Q6): an MCP server the core passes to every agent in `session/new`, in three tiers. The tiers are design requirements, enforced by the core on every call whatever the agent asks or claims (§5.3).
  - **Observe:** read settings, list apps and windows, read the selection, take a screenshot of non-secure windows. Observe is not harmless: these can show messages, names and documents, so each one has a scope and a destination (§5.3).
  - **Act, with consent each time or for the task:** change a setting from an allowlist; open, move or close windows; start a computer-control session for named apps.
  - **Never:** read secure windows; touch other apps' data; change security settings (lock screen, verified boot, developer options); install apps; send messages or make payments without the person doing it. The core refuses these tools outright. Computer control needs more than that, because a session on an approved app can tap anything in it (§5.3).
- **`quired`:** finds and runs the agent CLIs, adapts the ones without ACP, and confines the ACP file reads and writes it serves to the session's folder. It is not a sandbox: agents run as the person's user (§5.2). It runs where the agents can run. Agent CLIs are Linux (glibc) programs, so on the laptop that means the **Linux environment**: AOSP 17's AVF Terminal and its Debian guest (§4.1).
- **Connectors**, in order:
  1. local ACP agents through `quired` in the Linux environment (§4.1);
  2. a paired computer's `quired`, for people whose agents live on another machine, or whose laptop can't run the Linux environment. Designed, not built: [`docs/quire-pairing.md`](quire-pairing.md). The Checker held the design (TLS session resumption skips the pin check; the pairing code must bind both identities), so it is revised before it is built;
  3. direct cloud APIs with the person's own key, through a small agent loop in the core, for people with no CLI at all.

  Quire tries them in order and says why each one can't be used: no AVF in the image, no KVM, the Linux environment off, not installed, stopped or failing, nothing paired (`agents/Connectors.kt`). It never fails silently.

### 4.1 The Linux environment and `quired serve` (Q4, ANAL-218)

```text
Quire core (platform_app)                 Terminal app (vmlauncher_app)              Debian guest (crosvm, KVM)
  AgentHost: ACP client  --socket pair-->  AgentBridgeProvider  --------vsock------->  quired serve :7690 -> agents
  ContentResolver.openFileDescriptor(       relays bytes both ways, half-closes too   peer must be CID 2 (Android)
   content://…agentbridge/vsock/7690)       only port 7690 is offered
```

- **AVF in both products.** AOSP's generic system product carries the `com.android.virt` APEX, but builds it without AVF (no crosvm, virtmgr or Terminal app) unless the product inherits AVF's `product_packages.mk`; the phone Cuttlefish products do, the PC one did not (C). `device/anybook/common/linux-env/linux-env.mk` does, from `desktop.mk`. cp2a already enables the AVF release flags (custom VMs with paravirtualized devices, networking). The Terminal app ships disabled, as in AOSP: the person turns on **Developer options › Linux development environment**.
- **KVM.** Cuttlefish's launcher sets `ro.boot.hypervisor.vm.supported=1` on x86 (C). On a PC nothing did, so the PC product's `init.openbook.rc` runs `openbook-pc-setup kvm` at `post-fs`, which reads whether KVM registered its device (sysfs: only crosvm and ueventd may stat `/dev/kvm`), and sets the `ro.boot.hypervisor.*` properties only then. A G14 with SVM off in its firmware is not offered a Linux environment that can't start; Quire says "no hardware virtualization" and names the fallback.
- **The guest image is built here** (`scripts/quire/linux-env-image.sh`), with AOSP's own builder (`packages/modules/Virtualization/build/debian/`) and OpenBook's patch (`quire/linux-env/image/build-debian.patch`): Debian 13's own cloud kernel and initrd instead of a kernel downloaded from Google's CI, `quired` installed as a `.deb` with a systemd unit (user `droid`, vsock port 7690), and `socat`, which AOSP's ttyd bridge needs but its builder doesn't install. A test image may carry a pinned, checksummed agent (opencode, MIT); a product image ships none. On a debuggable build the Terminal app installs it from `/sdcard/linux/images.tar.gz`. On an installed OpenBook, such as the G14 since ANAL-223, `scripts/quire/linux-env-adb.sh push` puts it there over adb and checks its sha256 on the device. It refuses while a Linux environment is installed, because replacing one deletes the guest's files; the person does that in the Terminal app's Recovery settings. `linux-env-adb.sh check` then runs Q4's on-device check (`q4-device-check.sh`) and pulls its results. The builder works in its own folder (`WORK/work`, its `-W`); while it runs, `scripts/quire/unmount-build-loops.sh` undoes a desktop automounter's mounts of that folder's two loop-backed files, and of nothing else. The guest's `cidata.iso` (its guest agent and cloud-init files) is AOSP's checked-in one (`TerminalApp/assets-x86_64`, build 15101902); building it from source needs a musl host build (open).
- **How Quire core reaches `quired`.** Only a VM's owner may have a vsock to it: AVF's policy forbids creating vsock sockets outside AVF's own domains and the Terminal app (`domain.te`), and lets other apps only read and write sockets their own `virtmgr` made (`virtualizationservice_use`; C). So the Terminal app, which owns the VM, connects to the guest's port 7690 itself, as its ttyd bridge (`AndroidToVmBridge`) does, and relays the connection to one end of a socket pair; Quire core gets the other end through a content provider (`aosp/patches/packages/modules/Virtualization/0001`). It does not use `virtmgr`'s `VirtualMachine.connectVsock`: the owner may only read and write that socket, and passing on Quire's hang-up as a half-close needs `shutdown` (Cuttlefish showed the denial). A passed, connected unix socket between apps needs no new SELinux policy (`binder_call(appdomain, appdomain)`, `appdomain:unix_stream_socket` read/write; C, no denial in Cuttlefish).
- **`quired serve`** is one ACP agent towards Quire core that routes each session to an agent installed in the guest (`session/new` with `_meta.quire.agent`), and lists and describes them with two extension methods, `_quire/agents` and `_quire/describe`, as ACP's extensibility rules allow (C, agentclientprotocol.com/protocol/extensibility). `authenticate` is passed to the agent, and an `auth_required` error from `session/new` carries the agent's `authMethods`, so Quire can show each agent's sign-in. Terminal-type methods (run the agent's own login interactively) are never sent through `authenticate`, as ACP requires: the person signs in from the Terminal app.

## 5. Security and privacy

Q1 is a harness for **trusted local agents**. This section separates what Q1 enforces from what it does not, and from what later milestones must enforce before they ship.

### 5.1 What Q1 enforces (C, tested, §6)

- **Mediated file access stays in the session's folder.** When `quired` serves ACP `fs/read_text_file` and `fs/write_text_file`, every open and create goes through a handle on that folder (Go's `os.Root`), and so does creating parent folders. `..`, symlinks (dangling ones included) and a component swapped after the check cannot lead outside it. Only regular files are read or written.
- **Questions an agent asks reach the person, and fail closed.** `session/request_permission` and Claude's permission tool go to the person. The answer is "deny" or "cancelled" when nobody can be asked (no terminal), when the turn is cancelled, and when the bridge can't be reached.
- **Cancel is bounded.** Sending `session/cancel` and waiting for the agent to stop share one deadline, so an agent that stops reading can't stall it. An agent that hasn't stopped by then is stopped with its process group (SIGTERM, then SIGKILL) and reaped.
- **The permission bridge is private:** a 0600 socket in a 0700 folder. Ending the turn closes every connection on it, half-sent ones included.

### 5.2 What Q1 does not enforce

- **Agents run with the person's full access.** Agent CLIs run as the person's user, with `quired`'s environment and the person's files, commands and network. They can use all of that without asking `quired`.
- **Asking is the agent's choice.** In ACP v1 the agent MAY call `session/request_permission` before a tool call; nothing requires it. `quired` serves `fs/write_text_file` without asking the person, because the agent's own policy is what asks. In the ANAL-217 review a synthetic agent wrote a file with no question asked.
- **Claude's bridge sees only what Claude sends it.** A tool that Claude Code's own settings already allow runs without a question.

### 5.3 Requirements before Quire acts on the system (design, Q2–Q6)

- **Opt-in:** no agent is connected until the person connects it, and every note names the agent answering.
- **The broker authorizes every privileged call.** Quire core checks each OS-tool call against the person's grants when it is made, independent of the agent. An agent cannot grant itself anything. "Allow for this task" covers one tool for one task. Deny, cancel, a timeout and an unreachable person all mean no.
- **The never tier is enforced by mechanism, not by asking.** Refusing never-tier tools is not enough. In a computer-control session the agent injects arbitrary input into an approved app, so in a mail app it could send, in a wallet pay, and in Settings change security options. So, before Q6 ships computer control:
  - an app where the agent could send, pay or change security settings is not a target until Quire can recognise those steps and hand them to the person (`handOverApplications()`);
  - targets come from a Quire allowlist, and the platform's strict activity policy keeps sessions to them;
  - Q6 tests deny, cancel and each never-tier operation at the broker, and each must fail.
- **Observe is disclosure.** Screenshots, the selection and window lists can contain messages, names and documents. Each disclosure has an explicit scope (the window or region the person invoked Quire on) and destination (the named agent, and whether it runs locally or in the cloud). Both are shown to the person before anything is sent.
- **Secure content stays dark.** Windows with `FLAG_SECURE` are excluded from screenshots, and computer-control sessions block on them (platform behaviour, §2.4).

### 5.4 What Q4 adds at the vsock boundary (C, tested, §6.1)

- **Who can reach `quired` in the guest.** Only Android: `quired serve` refuses vsock peers other than CID 2, so a process in the guest (vsock loopback) or another VM gets nothing. On Android, only AVF's domains can open a vsock, and only the VM's owner, the Terminal app, gets one to this VM. It offers it on to callers holding `ACCESS_AGENT_BRIDGE` (signature|privileged, granted to Quire by its privapp allowlist), and only for port 7690: ttyd and the guest agent stay the Terminal app's own.
- **What Quire core can ask of `quired`.** Sessions run in folders inside `--root` (the guest user's home); a `cwd` outside it, or reached through a symlink out of it, is refused. A `session/new` without `cwd` gets a new folder under `Root/Quire`. The real path of `Quire` must be inside Root too, and the folder is created through a handle on Root (`os.Root`), so a `Quire` that links out of Root is refused before anything is created (ANAL-217's review of PR #111). MCP servers named by the client are refused: a stdio MCP server is a command line `quired` would run, and Quire's OS tools get their own shim in Q6.
- **Permission answers.** A request the client can't answer (gone, timed out) is refused with the agent's own reject option; an answer that isn't one of the agent's options is refused too. Quire core answers with the person's choice among the agent's own options, or by a fixed policy in the scripted checks; with nobody to ask, it refuses.
- **Lifetime.** When Quire core's connection ends, `quired` cancels every running turn and stops every agent it started for it, including one that was still starting. `Serve` returns only once they have all stopped.
- **Still the trusted-agent contract (§5.2).** Agents in the guest run as `droid` with that user's full access, including `sudo` without a password in AOSP's image. The guest is the boundary towards Android, not towards the agents.

### 5.5 Credentials and logs

- `quired` does not store, ask for or proxy agent credentials. Agents keep their own sign-in.
- `quired` is not a secret boundary:
  - It passes its whole environment to agents, so API keys in that environment reach them.
  - It relays raw tool inputs, message text, tool output and the agent's stderr to the client. `quired run --json` output and the evidence files keep them verbatim, so a secret an agent reads or prints can end up there.
- `quired` never logs its own environment. Evidence is redacted of home paths only, which is not secret redaction. Evidence is therefore scanned for common credential patterns before it is committed (a bounded check, not proof).
- Cloud keys for the direct connectors will stay in the core, in Android Keystore (design, Q4 and later).

### 5.6 What we will not do

Bypass Play Integrity, DRM or licence checks; use Google's Gemini apps or Magic Pointer code; send screen contents anywhere the person didn't choose.

## 6. Built: `quired` 0.1 (Q1)

Code: [`quire/quired/`](../quire/quired/). Go, standard library only, static binary. Check: [`scripts/quire/live-check.sh`](../scripts/quire/live-check.sh).

```text
quired agents [--json]                       list the agents installed here
quired probe [--json] (--all | AGENT...)     start agents and open a session, without prompting
quired run [flags] AGENT PROMPT...           run one turn (--approve ask|read|all|none, --json, --cwd, --agent-arg)
```

- **`internal/acp`:** ACP v1 types, plus a JSON-RPC 2.0 connection over newline-delimited JSON.
  - Notifications arrive in order.
  - Requests run concurrently, so a person can take their time on a permission prompt.
  - It has no line-length limit and survives non-JSON output.
  - One goroutine does the writing, and every send waits for it with a context. A peer that stops reading can't hold a caller past its deadline, and closing the pipe ends the connection and fails pending calls.
  - Method names and enums were checked against the ACP SDK inside Cursor Agent 2026.10.14 and against the spec repository.
- **`internal/agents`:** a catalog of 12 agents, each with the CLI version we last checked and its protocol, and discovery.
- **`internal/harness`:**
  - `acpagent.go` runs an ACP agent as a subprocess in its own process group. It:
    - refuses an agent that chooses an ACP version other than 1;
    - serves `session/request_permission`, and serves `fs/read_text_file` and `fs/write_text_file` confined through `os.Root` (§5.1);
    - cancels with `session/cancel`, and answers any open permission request "cancelled", as ACP requires. Sending the cancel and the agent stopping share one 15 s deadline. Past it, the agent's process group gets SIGTERM, then SIGKILL 3 s later, and is reaped;
    - reports the agent's stderr when it fails.
  - `claude.go` adapts Claude Code's `-p --output-format stream-json --include-partial-messages` to ACP updates:
    - text and thinking deltas become message chunks;
    - `tool_use` and `tool_result` become `tool_call` and `tool_call_update`, with readable titles ("Read note.txt", "Run make test");
    - `TodoWrite` becomes an ACP `plan`;
    - a new message starts a new paragraph;
    - each session uses `--session-id` on the first turn and `--resume` after that.
  - Permissions use Claude's `--permission-prompt-tool`. `quired permission-mcp` is a one-tool MCP server on stdio that forwards each question to the running `quired` over a private unix socket (0600, in a 0700 folder). Ending the turn closes every connection on the socket, and the MCP side gives up when Claude Code goes away; either way the answer is "deny". "Allow for this session" is remembered per tool.

**Results on this host (C), Arch Linux, 2026-10-18** (`evidence/2026-10-18-quire/`, regenerated on the revised code after the ANAL-217 review):

| Check | Result |
|---|---|
| Unit tests (`go test -race`) | **22/22 pass.** They cover the protocol, discovery, the ACP agent and the Claude adapter. The fake ACP agent and fake Claude Code are the test binary itself; the fake Claude really starts `quired permission-mcp` and calls it over MCP. One test replays a real Claude Code 2.1.301 stream. Regressions for the ANAL-217 review: writes through dangling symlinks, symlinked folders, `..` links and FIFOs; a symlinked session folder; a peer that stops reading; an agent that ignores `session/cancel`, and one that stops reading and ignores SIGTERM; half-sent and unanswered bridge questions; an unsupported ACP version |
| `quired agents` | 11 of the 12 catalog agents installed. **7 run through quired:** Claude Code (adapter), and opencode, Copilot, Cursor, Kimi, Hermes and omp (ACP). 4 are not yet supported, each with the reason: Grok (no ACP server), Codex (its own app-server protocol), Antigravity (stream-json, adapter planned) and Pi (nothing machine-readable) |
| `quired probe --all` (ACP `initialize` + `session/new`, no prompt, no cost) | **opencode, Copilot and omp:** a real ACP v1 session each, in 1.7–2.4 s. **Cursor and Kimi:** `-32000 Authentication required`, because they are not signed in for ACP on this host. **Hermes:** `-32603`, with no model provider configured (its stderr says so). Claude goes through the adapter, so its row only shows the session it created |
| `quired run claude --approve all` (haiku) | Claude chose `Bash printf … > hello.txt`. The permission bridge asked and was allowed, and **hello.txt = "Hello from Quire"**. `end_turn` in 5.2 s |
| `quired run claude --approve none` | Bash was denied, then Write was denied. **No file was written.** Claude stopped and said both tools were refused. `end_turn` in 9.3 s |
| `quired run opencode --approve read` | "QUIRE OK" over native ACP, `end_turn` in 2.0 s (8.9 s and 3.1 s in earlier runs) |

**Not done yet:**

- the Codex, Grok and Antigravity adapters;
- passing Quire's OS-tools MCP server, which is Q6.

### 6.1 `quired serve` (Q4)

```text
quired serve [--vsock PORT | --unix PATH | --stdio] [--root DIR] [--max-conns N]
quired agents --connect ADDR                 list the agents of a quired serve (vsock:CID:PORT or unix:PATH)
quired run --connect ADDR [flags] AGENT PROMPT...
```

- **`internal/serve`:** the router (one ACP connection, many agents and sessions), and `Remote`, the same client in Go that `--connect` uses and that Quire core's `AgentHost` mirrors in Kotlin. Updates an agent sends about a session before `session/new` has returned are held and delivered in order on both sides.
- **`internal/vsock`:** `AF_VSOCK` with the standard library only. `syscall` can't decode a vsock address, so bind, connect and `accept4` are raw system calls on non-blocking sockets in Go's poller.
- **Guest packaging:** `quire/linux-env/` (`build-deb.sh`, `quired.service`). On an installed system the image goes in over adb: `scripts/quire/linux-env-adb.sh` (§4.1).

## 7. Milestones

Each one is a sub-issue of ANAL-214 with its own acceptance checks. "G14" means checked on the laptop through the owner's stick, as with every other OpenBook milestone.

| # | Milestone | Owner | Done when |
|---|---|---|---|
| Q1 | **`quired` harness host** (ANAL-214) | Porter | Built and checked on this host (§6), this PR |
| Q2 | **Platform hooks in the image** (ANAL-216). Quire core skeleton as a privileged system app: `ROLE_ASSISTANT`, contextual search package, `ACCESS_COMPUTER_CONTROL` allowlist, the shake flag and the computer-control flags in OpenBook's flag set | Porter | In Cuttlefish: a shake and Meta+Space open Quire with a screenshot and the visible packages; a computer-control session on Settings shows in an `InteractiveMirror`; with per-app consent on, through the ordinary allowlist path (not a debug super agent): fresh consent, a second unapproved app, denial, secure content, lock and take-over; no new SELinux denials; the release flags diff reviewed. **Done in Cuttlefish (§2.6)** |
| Q3 | **Interaction and motion design** (ANAL-215) | Atelier | Invocation, the note's states (asking, streaming, steps, consent, mirror, done, error), motion specs and a clickable prototype; the visual language matches OpenBook's look |
| Q4 | **The Linux environment and `quired serve`** (ANAL-218). AVF Terminal in OpenBook, KVM on AMD, `quired` in the Debian guest, ACP over vsock to the core, pairing for a second computer | Porter | An agent installed in the Linux environment answers a prompt from Quire core in Cuttlefish, then on the G14. **Done in Cuttlefish (§4.1):** 29/29, and 8/8 without KVM; installed over adb, 0 failures. Open: the G14 run, over adb once the installed system's update carries AVF (`scripts/quire/linux-env-adb.sh check`), and pairing (design held for revision) |
| Q5 | **The surface** (ANAL-219). The note, steps, consent and mirror, built to Q3's spec | Porter with Atelier | Q3's states, in a recorded Cuttlefish session; 60 fps on the G14; works with TalkBack and keyboard only |
| Q6 | **OS tools over MCP** (ANAL-220). Settings (allowlisted, with undo), apps and windows, computer control | Porter | A scripted matrix: "turn on dark theme", "make text bigger", "open Files and show Downloads", each with the right consent, plus deny, cancel and never-tier refusals tested at the broker (§5.3) |
| Q7 | **Voice** (ANAL-221). Hold to talk, on-device speech-to-text (open models only), and the note reading back | Porter | Works offline on the G14; the mic indicator is always shown |
| Q8 | **Review and verification** (ANAL-217) | Checker | A security and privacy review of each PR against §5, and the G14 checklist results recorded |

The order is Q1, then Q2 and Q3 in parallel, then Q4 and Q5, then Q6 and Q7. Q8 runs alongside all of them.

## 8. Risks and open questions

In the order the ANAL-217 review ranked them, with what Q2 found.

1. **Policy enforcement and confinement.** Q1's file confinement, cancel bounds and bridge shutdown are fixed and tested (§5.1, §6). The rest is design (§5.3): authorization at the broker on every call, constraints on computer control for the never tier, and scoped disclosure for Observe. No OS tool ships without deny, cancel and never-tier tests at the broker.
2. **Computer control is `@hide` and partly flagged off in cp2a** (C). Q2 turned on `computer_control_access`, `_support_v5` and `_per_app_consent` and checked them in Cuttlefish through the ordinary allowlist path (§2.6). **What held:** sessions, consent, the lock-screen and secure-content refusals, the mirror, screenshots, taps and hand-over, with no crash or new denial. **What didn't, out of the box:** the allowlists need a configuration server, the consent dialog is not installed, and the session's accessibility tree never worked (an AOSP bug). Each is fixed in §2.5. Still open:
   - **An app that is already running on the person's display has no accessibility tree in the session** (C: 0 windows in four tries, 2 windows whenever Settings started fresh on the session display). Cause: HYPOTHESIS, the running process is not tied to the virtual device's accessibility clients. Quire's checks start the app fresh; Q6 must handle it (start the target fresh, or work from screenshots) and we should report it upstream.
   - **Release keys.** The session owner allowlist pins Quire's certificate, today AOSP's test platform key. An image signed with release keys needs its own digest in `session_owner_allowlist.txt`, or computer control stays off (it fails closed).
   - **Debuggable builds keep the last five invocation screenshots and session screenshots** in Quire's private storage, as Q2 evidence. User builds keep none. Q5 replaces this.
3. **The pointer shake and Meta+A/Meta+G were dead in AOSP 17 on a device like ours** (C): Launcher3 lacked `ACCESS_CONTEXTUAL_SEARCH`, and SystemUI armed the shake only for users who can log out (headless system user mode, which Googlebook runs and OpenBook does not). Both are patched (§2.5); the patches are small enough to send upstream.
4. **AVF on AMD.** In Cuttlefish (C): `kvm_amd` nested, crosvm on `/dev/kvm`, the non-protected Debian guest, vsock both ways, no denial for OpenBook code, and AOSP AVF's own denials listed (`evidence/2026-10-18-quire-q4/`). Found on the way: AOSP's PC product compiled AVF out; `virtmgr`'s vsock can't be half-closed by its owner; and without KVM, AVF and the Terminal app keep calling a dead VM running. Each is handled in §4.1. **On the G14, KVM is there:** a read-only adb check of the installed system (ANAL-214, 2026-10-18 23:36 UTC) found `/dev/kvm`, SVM on and `kvm_amd` loaded. **AVF and the guest on it are unproven.** AVF arrives with the next update over adb (ANAL-223), and the guest image (about 800 MB) is pushed the same way. `scripts/quire/linux-env-adb.sh check` then runs the KVM check, `kvm_amd`, the guest's boot time and the prompt there. It passes on Cuttlefish over adb, with 0 failures. The guest's network is Android's, through AVF's tethering, so the laptop needs Wi-Fi for cloud agents.
5. **Protocol compatibility and sign-in.** `quired` refuses ACP versions other than 1. Cursor and Kimi need an ACP `authenticate` step on this host. Since Q4, `quired serve` passes `authenticate` through and attaches each agent's `authMethods` to `auth_required`; Quire's connect screen (Q5) shows them. Agents whose only method is `terminal` (run the agent's own login) are signed in from the Terminal app.
6. **Agent CLIs change often.** The catalog records the version each entry was checked against, and adapters are only needed for agents without ACP. The industry is moving to ACP: 6 of the 11 CLIs on this host have it.
7. **The shake gesture is "early"** (its own TODO). We may tune the threshold for touchpads. In Cuttlefish a mouse shake of 8 strokes, 15 counts each, 50 ms apart, fires it on the first try.
8. **Contextual search also hands Quire a `MediaProjection`** (§2.3). Quire never uses it; a review should confirm it is never started.
9. **Naming:** "Quire" needs the same trademark check as "OpenBook" before any public image (`docs/STATUS.md`).

## Sources

- Google, "Introducing Googlebook, designed for Gemini Intelligence", 2026-05-12: https://blog.google/products-and-platforms/platforms/android/meet-googlebook/
- Agent Client Protocol, spec and SDKs (Apache-2.0, protocol version 1): https://github.com/agentclientprotocol/agent-client-protocol · https://agentclientprotocol.com. Permission requests are optional for the agent ("the Agent MAY request permission"), and cancel obligations: https://agentclientprotocol.com/protocol/v1/prompt-turn. Version negotiation: https://agentclientprotocol.com/protocol/v1/initialization. Both accessed 2026-10-18.
- Multica README and licence: https://github.com/multica-ai/multica
- Kernel: `common` at `fbfdd65b0fd1`, `arch/x86/configs/gki_defconfig`.
- Agent Client Protocol, extensibility (`_meta`, `_`-prefixed extension methods) and authentication (`authMethods`, `authenticate`, terminal methods): https://agentclientprotocol.com/protocol/extensibility · https://agentclientprotocol.com/protocol/v1/authentication, accessed 2026-10-18.
- AVF in AOSP 17, our pinned tree (Virtualization `22f1c9ee92b1`): `apex/product_packages.mk` (`PRODUCT_AVF_ENABLED`), `build/apex/Android.bp` (the AVF-disabled APEX variant), `android/TerminalApp/` (`ImageArchive.kt` and `InstalledImage.kt` for the local image and its build id, `new2/core/VmController.kt`, `AndroidToVmBridge.kt`), `libs/framework-virtualization/.../VirtualMachine.java` (`connectVsock`), `build/debian/`; `system/sepolicy/private/te_macros` (`virtualizationservice_use`), `domain.te` (the vsock neverallow), `crosvm.te` (`/dev/kvm`), `app.te`; `device/google/cuttlefish/host/commands/assemble_cvd/bootconfig_args.cpp` (the hypervisor properties).
- AOSP 17 (`android-latest-release`, our pinned tree: frameworks/base `8f5dedd3edc3`, Virtualization `22f1c9ee92b1`; paths as cited above): `frameworks/base/core/java/android/companion/virtual/computercontrol/`, `frameworks/base/packages/SystemUI/src/com/android/systemui/contextualcursor/`, `frameworks/base/core/java/android/app/contextualsearch/ContextualSearchManager.java`, `frameworks/base/services/contextualsearch/`, `frameworks/base/services/companion/java/com/android/server/companion/virtual/computercontrol/ComputerControlAllowlistController.java`, `frameworks/base/packages/VirtualDeviceManager/`, `build/release/aconfig/{cp2a,trunk_staging}/`, `packages/modules/Virtualization/`
- Rambler: secondary report of Google's 2026-09-21 post (R): https://letsdatascience.com/news/google-details-magic-pointer-and-rambler-features-for-google-978edf8d
