# Quire setup: agents in a few clicks (ANAL-393)

As of 2026-11-06. This is the design of Quire setup: a short wizard that gets the Linux environment ready, installs
the agents a person picks, signs them in and checks that one answers. After setup, the same window is where agents
are managed. It is built (ANAL-393) and checked in Cuttlefish; the G14 gets it with the next release. Not built yet:
the Quire card on OpenBook setup's Extras page (§4.4) and the Settings tile (§2.1). How Quire works is
[`quire.md`](quire.md); the note's design is [`quire-design.md`](quire-design.md).

Labels: **C** = confirmed (read in our AOSP 17 tree or our code, or ran it), **R** = from the maker's documentation,
**HYPOTHESIS** = not yet tested.

- **Prototype:** [`quire-setup-design/index.html`](quire-setup-design/index.html) shows every screen in light and dark.
  Add `?play=1` to click through the whole flow (downloads and installs are simulated), or `?screen=<id>` for one
  screen. It uses the note's tokens: glass, paper, ink and the holographic rim.

## Summary

- **Today, setup is unfinished and needs a developer to get through it (§1).** Quire's app icon opens a test window.
  The note can turn on the Linux environment, but installing an agent means opening Terminal and knowing the maker's
  command. Several agents can only be signed in from Terminal. On a `user` build the Terminal app
  downloads Google's Debian image, which has no `quired`, so Quire never finds an agent at all.
- **The fix: one window, four steps, one main button per step (§2).**
  1. **Linux:** one click turns it on, downloads it, checks it and starts it, with real progress.
  2. **Agents:** pick from cards. Quire installs each one with its maker's own installer.
  3. **Sign in:** each agent signs in in the browser with its maker. The window shows the device code, or a field
     for the code to paste back.
  4. **Try it:** a real first request, the default agent, and how to call Quire.

  After setup, the Quire app opens on the agents: add, update, sign out, remove, choose the default.
- **What changes underneath (§4):**
  - **The Terminal app** installs OpenBook's own guest image on every build type. It stages and resumes the
    download, checks the whole file against a SHA-256 pinned in the system image before it extracts anything, and
    extracts only names that pass its checks. It reports progress.
  - **`quired`** learns to install, update and remove agents and to run their sign-in, still without root.
  - **A narrow root worker** in the guest takes only three fixed operations, and only from Android: Debian
    prerequisites from a fixed list, `quired` updates, and reading a job's result.
  - **Quire core** gets the wizard and the agents page. The note's "no agent" card opens the wizard.
- **Needs B Honey once (§7):** a licensing call to include OpenBook's guest image (Debian 13 and `quired`, no agents,
  about 790 MB) in releases, with its complete source bundle. Each release still has its own publishing approval.
  Until then, previews keep sideloading the image over adb, and a `user` build says plainly that it has no Linux
  environment image yet.
- **Milestone:** M3 · Experience parity. The guest image part also decides whether Quire has agents at all in M2's
  `user` build, so M2 lists it.

## 1. What is wrong today (C)

| Where | What happens | Source |
|---|---|---|
| The **Quire** icon in All Apps | Opens `ControlActivity`, the Q2/Q4 test window: the computer-control session, a mirror, a prompt box. It is the only launcher entry Quire has | `quire/app/AndroidManifest.xml`, `control/ControlActivity.kt` |
| The note, no Linux environment | "Set up the Linux environment" turns it on and starts the install. This part works | `agents/Connectors.kt` `setUp` |
| The image it installs | Only a debuggable build reads `/sdcard/linux/images.tar.gz`. Otherwise the Terminal app downloads `dl.google.com/android/ferrochrome/5100000/x86_64/images.tar.gz`, Google's image, which has no `quired`. The download is checked only by HTTPS | AOSP 17 `TerminalApp/ImageArchive.kt` |
| So, on a `user` build | Quire finds no agent, ever, and the note says the Linux environment failed | `Connectors.kt`, `Agents.kt` |
| The note, no agent installed | "It hasn't found one yet." Nothing says what to do next | `strings_note.xml` `q_noagent_none` |
| Installing an agent | The person opens Terminal and types the maker's command | `quire-howto.md` |
| Signing in | ACP methods work in the note. Agents whose only method is their own login command must be signed in from Terminal | `quire.md` §4.1, §8 item 5 |
| Updating `quired` | Only a new guest image does it, and that deletes the guest's files | `quire.md` §6.1 |
| Removing or updating an agent | Terminal only | — |
| Root in the guest | `quired.service` sets `NoNewPrivileges=yes`, so nothing `quired` starts can use `sudo`, despite the guest's passwordless `sudo` | `quire/linux-env/quired.service` |
| Installing the image | `ImageArchive.installTo` writes each tar entry to `dir.resolve(name)` with no check on the name, and marks the install complete only at the end | AOSP 17 `TerminalApp/ImageArchive.kt` |

## 2. The flow

The wizard is one window of Quire core: 960 × 700 dp, centred, with the note's glass and holographic rim, over a light
scrim. A row of four steps sits in the header: Linux · Agents · Sign in · Try it. Each page has one title, one line
under it, and one main button at the bottom right. A step that is already done is skipped with its tick shown, so a
person who already has the Linux environment starts at Agents.

| # | Page | What the person does | What Quire does | Screens |
|---|---|---|---|---|
| 0 | **Welcome** (first time only) | Get started, or Not now | Checks in the background: AVF in the image, KVM, network, free space. "Downloads about 800 MB, once." | `welcome` |
| 1 | **Linux** | Nothing, or closes the window | Turns on the Terminal app, then downloads, checks, unpacks and starts the guest, and waits for `quired` to answer. Five rows tick in turn under a ring: this laptop can run it, downloading (MB done, time left), unpacking, starting Linux, connecting Quire. Closing the window doesn't stop it; a notification says when it's ready. | `linux` |
| 1′ | **Linux can't run** | Follows the steps, then Check again | No KVM: what to change in the firmware (SVM Mode or Intel VT). No network: Open Wi-Fi settings. Not enough space: how much to free. Failed: Try again, with the reason behind Details. Each is the reason `Connectors` already reports, worded for people. | `linux-nokvm` |
| 2 | **Agents** | Selects cards, then Install. **What will run**, beside the count, lists each selected agent's source and exact commands before anything runs | Lists `quired`'s catalog. Each card shows the maker and what the agent needs ("Free models, no account", "A GitHub account with Copilot"). Installed agents show their version. Agents Quire can't run yet (Codex today) are named under the grid, not offered. opencode is marked "Good first pick": it needs no account. | `agents` |
| 2′ | **Installing** | Waits, or keeps working | Installs one agent at a time. Each card shows its own progress and the current step in words ("Downloading GitHub's installer"). Show details lists the exact commands and their output. A failure stays on its card with Try again; the others carry on. | `installing` |
| 3 | **Sign in** | Sign in on each row, or Later | One row per installed agent: Ready (no account needed), Signed in, or Sign in. | `signin` |
| 3′ | **Device code** | Copies the code, opens the page | Shows the maker's one-time code large with Copy, and a button that opens the maker's page in the browser. It waits and closes by itself when the agent reports success. | `signin-device` |
| 3″ | **Paste back** | Opens the page, pastes the code | Opens the maker's page in the browser, gives the code to the agent's own login, and closes on success. "Use an API key instead" where the agent supports a key (§5). | `signin-paste` |
| 4 | **Try it** | Reads, picks the default agent, Done | Sends one real request, "Introduce yourself in one sentence.", to the default agent and streams the answer in ink. Beside it: how to call Quire (shake the pointer, Meta+Space), animated. | `try` |
| — | **Agents page** (the Quire app after setup) | Manages | The Linux environment (running or stopped, `quired` version, space used, Stop or Start), the agents (version, sign-in state, a star for the default, a menu: Update, Sign in again, Sign out, Remove), Add agents, and Open Terminal for anything else. | `manage` |

**Rules:**

- **One main button per page.** It's always bottom right and always says what it does ("Install 2 agents", not
  "Next").
- **Every wait shows real progress** in bytes or steps, from the component doing the work. Nothing is a spinner
  without words.
- **Every dead end has a way out** on the same page.
- **It never needs Terminal or Developer options.** Terminal stays available for anything the wizard doesn't cover.
- **Nothing is sent to an agent before the person connects it.** Installing it from the wizard counts as connecting
  it (`quire.md` §5.3). An agent found any other way is still listed as not connected.
- **The words are short and plain.** The maker's name appears only where the text is about that maker.
- **Keyboard and TalkBack** follow `quire-design.md` §8. Tab order is the reading order, Enter activates the focused
  button, Esc closes a sheet and then the window, and the steps row is a labelled list with `aria-current`-style state.
  The agents grid is checkboxes. Progress rows are a polite live region.
- **Remove animations** cuts every motion, as in the note.

### 2.1 Where it opens

| From | Opens |
|---|---|
| The **Quire** app in All Apps | The wizard until setup is done, then the agents page. `ControlActivity` stops being a launcher entry and stays as the debuggable-only lab alias the scripted checks use |
| The note's no-agent card ("Connect an agent") | The wizard at its first unfinished step. The inline "Set up the Linux environment" button is replaced by **Set up Quire** |
| The note's sign-in card, for an agent whose only method is its own login | The wizard's sign-in sheet for that agent, instead of "sign in from Terminal" |
| The agent picker's "Connect an agent" row | The agents page |
| OpenBook's first-run setup, Extras page | A Quire card: "Set up Quire when you start" (on by default when the laptop can run it). The wizard then opens once on the first desktop. Setup itself never waits for a download |
| Settings | **HYPOTHESIS:** Settings › System › Quire through Settings' injected-tile mechanism for a privileged app. Built only if AOSP 17's Settings shows it; otherwise the app entry is enough |

## 3. The design

The prototype is the reference. In short:

- **Material:** the note's glass at 80 % over the system's blur, its bloom and specular edge, and the 1.5 dp rim in
  the halo's hues. The rim turns while something is running. Cards and rows are paper. With the platform's blur off
  the window is 96 % paper, as the note is (`quire-design.md` §4.5).
- **Type:** titles are Google Sans 30/38 regular, the line under a title 15/22 soft ink, and body text 14.5/20.
- **Colour** is the device's dynamic roles. The brand gradient appears only on the leaf, the progress ring and bar,
  and the rim, as in the note.
- **The ring** on the Linux page is the halo drawn as a progress arc around the leaf, filling with the download and the
  steps. Ticks are drawn as strokes, as in the note's steps.
- **Avatars** are the note's initials on tonal discs. There are no makers' logos, so the design has no trademark
  question.
- **Motion:** pages change with `spring.settle`, the ring follows progress with the standard easing, and the "call
  Quire" demo loops a pointer shake into the halo. All of it cuts with Remove animations.

## 4. What changes underneath

### 4.1 The Terminal app: OpenBook's image on every build (`aosp/patches/packages/modules/Virtualization/0003`)

AOSP's `ImageArchive.installTo` streams the archive straight into the install folder. It writes each tar entry to
`dir.resolve(name)` without checking the name, and the only proof of completion is the marker file written at the
end (C). A hash checked "before the marker" would come after those writes. So the install is rebuilt as stage,
verify, extract, commit:

- **Which image.** The rules are decided in this order and never fall through to Google's image on OpenBook:
  1. **A debuggable build with `/sdcard/linux/images.tar.gz`** keeps today's path, for the checks. It is ignored
     when `ro.debuggable=0`.
  2. **OpenBook's image**, named by `/product/etc/openbook/linux-env.json` in the read-only system image: URL,
     SHA-256, compressed size, installed size and version.
  3. **The manifest present but with no URL** is the state before an image is published (§7). The status is
     `no_image`, and the wizard says "This build doesn't include a Linux environment image yet". The same happens when
     the manifest is unreadable or invalid, and it says that instead.
  4. **No manifest** on an OpenBook build is `no_image` too. The build is recognised as OpenBook's by Quire core
     being installed (`/system_ext/priv-app/OpenBookQuire`), not by the manifest itself. Only a build that isn't
     OpenBook's keeps AOSP's behaviour (Google's image).
- **Stage.** The download goes to a staging file in the Terminal app's no-backup storage (`linux-staging/`), never
  into the install folder. A small `staging.json` next to it records the manifest's URL, hash and size.
- **Resume after a restart.** On the next start, if `staging.json` matches the manifest, the bytes already staged are
  hashed, and the download continues with `Range: bytes=<length>-`.
  - It continues only on a `206` whose `Content-Range` starts at that length.
  - A `200`, any other range or a changed manifest starts over from zero.
  - Today's range support keeps the offset only in memory, so it can't survive the process ending. This one can.
- **Verify.** The extraction starts only after the whole compressed archive matches the pinned size and SHA-256. A
  mismatch deletes the staging file and reports `error` with the reason. Nothing has been written to the install
  folder by then.
- **Extract only names that pass the checks.** The archive is extracted into a fresh sibling folder
  (`<install>.new`). An entry is refused, and the whole extraction with it, when:
  - its normalized path is absolute, contains `..`, or resolves outside that folder;
  - it isn't a regular file or a directory (symlinks, hard links, devices and FIFOs are refused);
  - its name isn't one AOSP's installer knows (`build_id`, `root_part`, `vm_config.json`, `vmlinuz`, `initrd.img`,
    `efi_part`, `cidata.iso`, `cidata.build_id`);
  - the running total passes the manifest's installed size.
- **Commit.** The marker is written in `<install>.new`, and then it is swapped in by rename. Any failure deletes
  `<install>.new`, so an existing guest is never touched until a complete, verified one is ready.
- **Space.** Before starting, it checks that there's room for the compressed size plus the installed size, with a
  margin, and says how much to free if not.
- **Progress through the bridge:** `status` and `start` also return `phase` (`download`, `verify`, `unpack`, `start`),
  `bytes` and `total`, and `stop` is added. The wizard reads these and invents nothing.
- **The bridge offers one more port,** 7691, for the admin worker (§4.3). It has the same permission and the same
  relay as 7690.
- **Why pinned:** AOSP allows `/sdcard` only on debuggable builds because any app can write there. A hash pinned in the
  read-only system image keeps that guarantee on `user` builds and covers the download too.

### 4.2 `quired`: install and sign-in (`quire/quired/internal/setup/`)

`quired` keeps running as `droid` with `NoNewPrivileges=yes` (C, `quire/linux-env/quired.service`), so neither it nor
any agent or installer it starts can gain root, `sudo` included. Nothing here changes that. New ACP extension methods
sit next to `_quire/agents` and `_quire/describe`, on the same connection over vsock 7690:

| Method | What it does |
|---|---|
| `_quire/catalog` | Every catalog agent: name, maker, what it needs, whether Quire can run it, whether it is installed (path, version), its sign-in kinds, and its recipe as text: each step's command and source URL, so the wizard can show it before Install |
| `_quire/install {agent}` | Runs the agent's recipe (§5) as `droid`, in its own process group, with a deadline. Progress arrives as `_quire/progress` notifications (step, bytes when known, the last output line). Ends with the version found, or the failing step and its output. A recipe that needs Debian packages says so first, and Quire core asks the admin worker for them (§4.3) before calling this |
| `_quire/update {agent}`, `_quire/remove {agent}` | The same, with the maker's update or uninstall method |
| `_quire/login {agent, method}` | Runs the agent's own login command on a pseudo-terminal. `quired` reads its output and sends `_quire/login/prompt` with what it found: a URL to open, a device code, or "paste a code". The redacted output is in Details. It ends when the command exits, then checks the sign-in state |
| `_quire/login/input {text}` | Writes the pasted code to the login's terminal (§6) |
| `_quire/key {agent, name, value}`, `_quire/signout {agent}` | Stores or removes an API key for one agent (§6). Sign-out also runs the maker's logout command where there is one |
| `_quire/signin {agent}` | Whether the agent is signed in, by its own status command where it has one, else by a no-prompt `session/new` |
| `_quire/cancel {job}` | Cancels a running install or login: SIGTERM to its process group, then SIGKILL 3 s later, as for agents (`quire.md` §6) |

- **Recipes live in the catalog**, next to the version each one was last checked against, with the source URL and date
  of the maker's instructions. A step is a Debian prerequisite (handled by the worker, never `sudo`), an npm package
  (`npm install -g --prefix ~/.local …`), a versioned download with a checksum, or the maker's install script fetched
  over HTTPS and run with `bash`. An installer that tries `sudo` itself fails at that point. For example, Hermes runs
  `sudo -n` for `libatomic1`, so its recipe gets `libatomic1` from the worker first.
- **PATH:** installs go to `~/.local`. `quired.service` adds `~/.local/bin` and the makers' own folders to the
  agents' `PATH`, so a new agent is found without a restart.
- **The pseudo-terminal** uses only the standard library (`/dev/ptmx` with `TIOCSPTLCK` and `TIOCGPTN`), as `quired`
  already does for vsock.
- **Logs:** each job writes `~/.local/state/quire/jobs/<agent>-<time>.log` in the guest, redacted as §6 says.

### 4.3 The admin worker: Debian packages and `quired` updates (`quired admin`)

Two operations need root: installing a Debian prerequisite, and updating `quired` itself. `quired`'s package
`postinst` restarts `quired.service` (C, `quire/linux-env/deb/postinst`), so an update launched from inside that
service could be killed half-way. Both move to a separate, narrow worker:

- **The units:**
  - `quire-admin.socket` listens on vsock port 7691 (`ListenStream=vsock::7691`, `Accept=yes`; **HYPOTHESIS**:
    Debian 13's systemd 257 accepts vsock in socket units, as `systemd.socket(5)` documents).
  - `quire-admin@.service` runs `quired admin` as root, once per connection, with its own hardening (`ProtectHome`,
    `PrivateTmp`, and write access only where it needs it).
  - It is a separate unit from `quired.service`, and `postinst` restarts only `quired.service`.
- **Who may ask:** only the host. The worker checks that the peer's CID is 2 (Android) and closes anything else, the
  same rule `quired serve` applies on 7690.
  - An agent in the guest can only reach it through local vsock (CID 1), so it is refused.
  - On Android, only Quire core can open the bridge's 7691, because it holds the bridge permission.
  - `quired` and the agents never talk to the worker.
- **What it does:** three operations, nothing else, and no shell.
  - `debian-install {packages}` takes only names on a list built into `quired`: `ca-certificates`, `curl`, `git`,
    `tar`, `xz-utils`, `unzip`, `libatomic1`, `nodejs`, `npm`. It runs `apt-get install --no-install-recommends`
    from the image's own Debian sources, and refuses any other name.
  - `quired-update {deb, sha256}` takes a package that Quire core carries in the system image, with its pinned hash.
    The worker checks the hash, that the package is named `quired` and is for this architecture, and that its version
    is newer. Then it hands `dpkg -i` to a transient unit (`systemd-run --unit=quire-update-<id> --collect`). That
    install outlives both `quired`'s restart and the connection. The result goes to `/var/lib/quire/jobs/<id>.json`
    (root, 0700), and Quire reads it on its next connection.
  - `job {id}` reads such a result.
- **Why not `sudo` from `quired`:** that would mean dropping `NoNewPrivileges`, which would give every agent a way to
  root. The worker keeps the agents unprivileged, and only accepts fixed operations from Android.
- **Old guests:** the G14's guest has `quired` 0.3.0, which has neither the worker nor the new methods, and can't be
  updated from Quire. The wizard says so. It offers a reinstall of the Linux environment, and says plainly that this
  replaces the guest's files. A developer can use `scripts/quire/linux-env-adb.sh` instead.

### 4.4 Quire core

- **`setup/`:** `SetupActivity` (the window), `SetupModel` (a state machine for the pages, kept across the restarts
  the framework does, as OpenBook setup's ViewModel does), and `AgentsPage`. Built with Quire's own `ui/` (palette,
  motion, widgets), so it looks like the note without a second toolkit. Secrets never enter saved state (§6).
- **The guest's `quired` stays current:** Quire core carries the `quired` package that matches it, as a raw resource
  with its SHA-256. On each connection it compares versions (`initialize`'s `agentInfo.version`). When the guest's is
  older, it sends `quired-update` to the worker (§4.3), then reconnects.
- **The note:** the no-agent card's button becomes **Set up Quire**; "It hasn't found one yet" becomes "Set up Quire
  to choose and install an agent". The terminal-only sign-in path opens the wizard's sheet.
- **A notification** "The Linux environment is ready" (or the reason it stopped), when the window was closed during
  step 1.
- **OpenBook setup:** the Extras page gets the Quire card (§2.1). A flag in Quire's preferences opens the wizard once
  on the first desktop.

### 4.5 What doesn't change

The broker, the OS tools, the consent rules and the note's states (`quire.md` §4.2, §10; `quire-design.md` §3) stay
as they are. Pairing a second computer stays a design under review.

## 5. The agents: install and sign-in

From the makers' documentation and the CLIs' own `--help`, checked 2026-11-06 (R, or "local" for `--help` of the
version named in `quired`'s catalog on our dev host). Nothing here was installed or signed in for this design. The
recipes are checked again in the guest when they're built (§8), and the catalog records the date.

**What changed since the catalog was last checked (2026-10-18):** every agent now has an installer that needs no root
and no Node.js, except Gemini CLI, which needs Debian's Node.js. Some makers also publish versioned binaries (§6).
Grok CLI (`grok agent stdio`) and Antigravity CLI (`agy acp`) now have ACP servers (C, `quired probe` on the dev
host, 2026-11-06: Grok answered ACP v1 `initialize` and `session/new` asked for sign-in; Antigravity opened a session
and offers its own `authenticate` methods), so they are supported with no adapter code. Gemini CLI's flag is `--acp`
(not run: it isn't installed on the dev host). Only Codex stays under "Coming to Quire". Antigravity signs in through
ACP's own `authenticate` (kind `acp` in the catalog).

| Agent | Install (as `droid`, no root unless noted) | Update · remove | Sign-in in the wizard | Key or token | ACP |
|---|---|---|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash`, to `~/.local/bin/claude` ([setup](https://code.claude.com/docs/en/setup)). The signed apt repository needs root and a third-party source, so it isn't used | `claude update`, or it updates itself · delete `~/.local/bin/claude` and `~/.local/share/claude` | `claude auth login`: open the URL, then paste the code the page shows back (paste-back is documented as the fallback; whether its default waits on a local port is unconfirmed) ([auth](https://code.claude.com/docs/en/authentication)) | `ANTHROPIC_API_KEY` | `quired`'s adapter (`claude.go`) |
| opencode | `curl -fsSL https://opencode.ai/v2/install \| bash` with its no-PATH-edit option, to `~/.opencode/bin`. **`opencode.ai/install` installs v1** ([v2 docs](https://opencode.ai/v2/docs)) | `opencode upgrade` · `opencode uninstall` (local 2.2.5) | None for its free models | Providers through `opencode auth login` | `opencode acp` |
| GitHub Copilot CLI | A pinned release binary, where GitHub publishes one with a checksum ([install](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)); else `curl -fsSL https://gh.io/copilot-install \| bash`, to `~/.local` ([install](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)) | `copilot update` · unconfirmed | `copilot login --device-code`: the code and github.com/login/device (local 1.0.106). Passed explicitly, because its default on a desktop waits on a local port | Fine-grained token in `COPILOT_GITHUB_TOKEN` | `copilot --acp` |
| Cursor Agent | `curl https://cursor.com/install -fsS \| bash`, to `~/.local/bin/cursor-agent` ([install](https://cursor.com/docs/cli/installation)) | `agent update` · not documented | `NO_OPEN_BROWSER=1 cursor-agent login` prints a link and polls; no code to copy ([auth](https://cursor.com/docs/cli/reference/authentication)) | `CURSOR_API_KEY` | `cursor-agent acp` |
| Gemini CLI | `nodejs` and `npm` from the admin worker (Node 20 or newer; Debian 13's version is a **HYPOTHESIS** to check), then `npm install -g --prefix ~/.local @google/gemini-cli` ([install](https://www.geminicli.com/docs/get-started/installation)) | npm `@latest` · `npm uninstall -g` | `NO_BROWSER=true`: open the URL, paste the code back. Its default waits on `127.0.0.1` ([oauth2.ts](https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/core/src/code_assist/oauth2.ts)). Free-tier Google sign-in moved to Antigravity on 2026-06-18 ([auth](https://www.geminicli.com/docs/get-started/authentication)), so the card asks for a key | `GEMINI_API_KEY` | `gemini --acp` ([ACP](https://geminicli.com/docs/cli/acp-mode/)); the catalog's `--experimental-acp` is out of date |
| Antigravity CLI | `curl -fsSL https://antigravity.google/cli/install.sh \| bash`, to `~/.local/bin/agy` ([start](https://antigravity.google/docs/getting-started)) | `agy update` · unconfirmed | A Google account. It prints a URL and asks for the code back only when it detects SSH, and no flag forces that ([install](https://antigravity.google/docs/install?tab=cli)). **HYPOTHESIS** that it does so on the guest's terminal; if not, Terminal until it has a flag | `GEMINI_API_KEY` with its `modelProvider` setting | `agy acp` ([ACP](https://antigravity.google/docs/cli/acp/)) |
| Kimi Code | `curl -fsSL https://code.kimi.com/kimi-code/install.sh \| bash` with `KIMI_NO_MODIFY_PATH=1`, to `~/.kimi-code/bin` ([guide](https://moonshotai.github.io/kimi-code/en/guides/getting-started)) | `kimi upgrade` · delete the binary | `kimi login`: a device code (local 2.4.1) | `KIMI_MODEL_API_KEY` | `kimi acp` |
| Grok CLI | `curl -fsSL https://x.ai/cli/install.sh \| bash`, to `~/.grok/bin` ([docs](https://docs.x.ai/build/overview)). It also makes an `agent` link, which clashes with Cursor's: `quired` runs both by their full names | `grok update` · unconfirmed | `grok login --device-auth` (local 1.0.77) | `XAI_API_KEY` | `grok agent stdio` ([headless](https://docs.x.ai/build/cli/headless-scripting)) |
| Hermes Agent | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash`, after `git`, `curl`, `tar` and `libatomic1` from the admin worker. It brings its own Python and Node ([install](https://hermes-agent.nousresearch.com/docs/getting-started/installation)). ACP needs one more documented step | `hermes update` · `hermes uninstall` | Nous Portal by device code, or a provider key ([providers](https://hermes-agent.nousresearch.com/docs/integrations/providers)) | `~/.hermes/.env` (`OPENROUTER_API_KEY` and others) | `hermes acp` ([ACP](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp)) |
| Oh My Pi | `curl -fsSL https://omp.sh/install \| sh`, to `~/.local/bin/omp` ([repo](https://github.com/can1357/oh-my-pi)) | `omp update` · unconfirmed | `omp login <provider>`: paste the code or URL back; Copilot by device code ([providers](https://omp.sh/docs/providers)) | `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` and others | `omp acp` |
| Codex CLI (coming) | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` ([repo](https://github.com/openai/codex)) | `codex update` | `codex login --device-auth` (beta, and the person turns on device codes in ChatGPT's settings first) ([auth](https://learn.chatgpt.com/docs/auth)) | `OPENAI_API_KEY` through `--with-api-key` | None. `quired`'s own adapter for `codex app-server` stays planned; a community ACP adapter exists and its licence is unchecked |

**Rules the recipes follow:**

- **Use the code-based sign-in** (device code or paste-back) wherever the maker has one, and pass its flag
  explicitly. A sign-in that only waits on a local port is never started from the wizard (§6).
- **Use the no-PATH-edit option** where an installer has one, and put each maker's folder on the agents' `PATH` in
  `quired.service` (`~/.local/bin`, `~/.opencode/bin`, `~/.kimi-code/bin`, `~/.grok/bin`). The guest's shell files
  stay the person's.
- **Uninstall** uses the maker's command where there is one. Otherwise it deletes only the paths that maker's
  installer created, listed in the catalog. It never deletes the agent's own settings and history unless the person
  asks ("Also delete its settings").

## 6. Security and privacy

- **What runs, and where:**
  - Every install, login and agent runs inside the guest as `droid`, under `quired.service`'s `NoNewPrivileges=yes`,
    never on Android. None of them can gain root, not even with the guest's passwordless `sudo` (C: AOSP's
    `cloud-init_config/user-data` grants it; the Checker reproduced the refusal with
    `setpriv --no-new-privs sudo -n -- true`, 2026-11-06).
  - Root work is limited to the admin worker's three fixed operations, requested only from Android (§4.3).
- **Makers' installers** (the Checker: allowed, as code the person picks that runs without privilege):
  - **Before Install,** "What will run", beside the count of selected agents, lists for each one the maker, the exact
    commands and where they're fetched from (prototype: `agents-details`). The same list stays in Details while it
    runs.
  - **Prefer verified, versioned downloads** where the maker publishes them and they need no root. For example,
    Copilot documents direct release binaries
    ([install](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli),
    accessed 2026-11-06). The recipe pins the version and checks a published checksum when there is one (to confirm
    for each maker when built).
  - **Otherwise the maker's documented script:** fetched over HTTPS from the maker's domain, which the catalog pins.
  - **Root-only methods are not used,** such as Claude Code's signed apt repository: the worker doesn't add
    third-party apt sources.
- **Sign-in:**
  - The password is typed only on the maker's page, in the browser.
  - What passes through Quire is a one-time code. A device-code flow shows its code and sends nothing. A paste-back
    flow writes the code once to the login's terminal.
  - Quire core keeps no code: not in memory after the write, not in saved state, not in a log.
- **API keys** (the Checker: allowed, with these limits):
  - **Which agents:** only those whose own documented settings take a key (§5).
  - **The path:** the key goes from a password field to `quired` over vsock. `quired` writes it to
    `~/.config/quire/keys/<agent>.env`.
  - **The files:** the folder is 0700, and the file is 0600.
    - It is created through `os.Root` with `O_NOFOLLOW`, as a temporary file renamed into place, so a symlink can't
      redirect it.
    - A folder or file that isn't `droid`'s, has the wrong mode, or is a symlink is refused, not repaired.
  - **Who gets it:** `quired` passes it only in the environment of the agent it belongs to, when it starts that agent.
    Other agents and logins don't get it.
  - **What 0600 doesn't do:** it isn't isolation between agents. Every agent runs as `droid`, so any of them can read
    another's key file. The wizard says so where it asks for a key.
  - **On Android:** the key is never in Android's saved state. The field doesn't save its state and isn't offered to
    autofill, `SetupModel` holds no key, and the screen is cleared when the sheet closes.
  - **Sign-out** deletes that agent's key file and runs the maker's logout command where there is one (§5). Where the
    maker has none, the agents page says which of the maker's files hold the login, and offers "Remove the agent and
    its settings".
- **Logs and Details:** everything a job prints is redacted before it reaches a log or the screen.
  - The bytes written to a login's terminal are cut from its echo.
  - Values that look like a key or token of a known maker are masked, as are the values of `*_API_KEY` and `*_TOKEN`.
  - Logs stay in the guest.
- **The image:** pinned by SHA-256 in the read-only system image and verified before anything is extracted (§4.1).
  Neither a file on `/sdcard` nor a changed download can replace it on a `user` build.
- **`quired` updates:** the package comes from the system image, with its hash pinned there. It travels over the
  vsock connection that only Quire core can open, and the root worker installs it in a unit of its own (§4.3).
- **Localhost sign-in:** a login that waits for the browser to come back to `localhost` in the guest can't finish,
  because the browser is on Android. The Terminal app would ask the person to allow forwarding of that port (C:
  `PortNotifier.kt`). The wizard uses the device-code or paste-back variant where the maker has one (§5), and
  otherwise says the agent signs in from Terminal for now.

## 7. The guest image in releases, and the request to B Honey

A release that pins the guest image also has to carry everything its licences require. The image isn't only Debian
packages. AOSP's builder adds parts that aren't in Debian's package list (C, `build/debian/build_internal.sh`,
`ttyd/cross-build.sh`):

- ttyd 1.7.7, built with AOSP's `xtermjs_a11y.patch`, and statically linked with musl, zlib 1.3.1, json-c 0.17,
  mbedtls 2.28.5, libuv 1.44.2 and libwebsockets 4.3.3;
- the guest agent in `cidata.iso`, AOSP's prebuilt, whose crates have their own licences.

ttyd's MIT licence requires its notice
([LICENSE](https://github.com/tsl0922/ttyd/blob/1.7.7/LICENSE)), and Debian requires each component's own licence to be
honoured ([FAQ](https://www.debian.org/doc/manuals/debian-faq/redistributing.en.html)), both accessed 2026-11-06.

**Packaging step:** `scripts/quire/linux-env-sources.sh` builds one source bundle per image, from the image's own
records, next to the image:

| Part | What it holds |
|---|---|
| `debian/` | The exact source packages (`.dsc`, original and Debian tarballs) of every package installed in the image, **the kernel included** (`linux`, for `linux-image-*-cloud-amd64`). The versions come from the image's dpkg status and are fetched from `snapshot.debian.org`, along with the list |
| `components/` | ttyd and each library above at its exact version, with AOSP's patch and `cross-build.sh`. The musl toolchain's source and version. The guest agent's AOSP source revision and its crates' licences |
| `build/` | AOSP's builder at the pinned revision, `quire/linux-env/image/build-debian.patch`, `scripts/quire/linux-env-image.sh` and `quire/linux-env/` (`quired`'s package and units), so the image can be rebuilt |
| `LICENSES/`, `NOTICE` | Every `/usr/share/doc/*/copyright` in the image, plus each component's licence and notice |

- **The image carries no agent.** The release image is built without `--test-agent`; only test images carry
  opencode.
- **The release lists both files** in `SHA256SUMS`, and `make-release.sh` checks that the bundle matches the image's
  package list before it signs anything.

**The request**, once the Checker passes it (not sent yet):

> **Licensing:** From the next release on, each OpenBook release also includes the Linux environment image that
> Quire's agents run in (Debian 13 with `quired`, no agents, about 790 MB), with its complete source bundle. The bundle
> has the exact Debian source packages including the kernel, ttyd and the libraries built into it with their licences
> and patches, the notices for AOSP's guest agent, and the scripts that build the image. Builds pin the image's address
> and SHA-256. Each release is still published only with its own approval. To undo: future builds stop pointing at the
> image, and the images and sources already published stay up so their licences are still honoured. Reply approve.

**Other decisions, settled by the Checker (2026-11-06):** makers' installers, yes (§6); API keys, yes, with §6's
limits; the Quire app opens the wizard first and the agents page after setup, and the test window stays only as the
debuggable-only lab alias.

## 8. Tests

| Check | What it covers | Where |
|---|---|---|
| `go test -race ./...` in `quire/quired` | Recipes run step by step, with the test binary standing in for `npm`, `curl` and the makers' scripts. Cancel, deadline, failure output, PATH. The pseudo-terminal. URL and code detection on recorded login transcripts. Redaction of echoed input and of key-like values. Key files: mode, owner, symlinked folder or file refused, passed only to their agent, deleted on sign-out. The worker: names off the list refused, a peer other than CID 2 refused, a wrong hash, name, architecture or an older version refused | Host, CI |
| `linux-env/tests/image-archive-test.sh` (new) | The patch's install classes on the JVM, with `debuggable=false`: `/sdcard` is ignored; a missing, invalid or URL-less manifest gives `no_image` and never Google's image; a wrong hash extracts nothing and leaves an existing guest untouched; `../`, absolute, symlink, hard link, device and unknown-name entries are refused with nothing written outside the staging folder; resume after a simulated restart, with servers answering `206`, `200` and a changed file; too little space | Host, CI |
| `device/anybook/common/quire/tools/unit-test.sh` | `SetupModel`: every page transition, skip rules, the restart in the middle of a download, the copy for each `Connectors` state, no secret in saved state | Host, CI |
| `scripts/quire/linux-env-qemu.sh --setup` (real services) | The guest's real systemd units, no mocks. The worker installs `git` from Debian and refuses a name off its list and a request from inside the guest (CID 1). It updates `quired` from the previous version to this one while `postinst` restarts `quired.service`; the job finishes and its result is read on the next connection. Then opencode is installed by its recipe and answers one prompt | Host QEMU |
| `scripts/quire/setup-walk.py` (new) | The wizard in Cuttlefish: every page in light and dark, the keyboard path, the labels, Remove animations, the no-KVM page (with `initcall_blacklist=svm_init`), the Terminal app killed half-way through the download and resuming, opencode installed and answering | Cuttlefish (`userdebug`) |
| The same, on a `user` build | `ro.debuggable=0`: an image in `/sdcard/linux` is ignored, the manifest with no URL shows "no image yet", a manifest pointing at a host server installs, a tampered file on that server is refused, and an existing guest survives the refusal. One `anybook_cf_x86_64_pc-cp2a-user` build serves it, and M2 needs that build anyway | Cuttlefish (`user`) |
| Release suite | One run on the G14 with a real sign-in (the owner's choice of agent) | G14, release |

Screens and logs go on the issue and in the evidence store, never in the repository.

## 9. Build order

One pull request, `feat(quire): set up agents from a wizard`, in reviewable commits:

1. `docs(quire)`: this design and its prototype.
2. `feat(quired)`: `internal/setup`, the catalog's recipes and refreshed entries (§5), the methods in §4.2, key files,
   redaction, and their tests.
3. `feat(quired)`: `quired admin` and its units (`quire-admin.socket`, `quire-admin@.service`), `postinst` restarting
   only `quired.service`, and the QEMU real-service check.
4. `feat(terminal)`: patch 0003: stage, verify, extract checked names, commit; durable resume; the manifest; progress,
   `stop` and port 7691; the JVM tests.
5. `feat(quire)`: the wizard, the agents page, the launcher entry, the note's card, the notification, and keeping
   `quired` current.
6. `feat(setup)`: the Quire card on OpenBook setup's Extras page.
7. `build(quire)`: `linux-env-sources.sh` and the release's checks of the bundle (§7).
8. `docs(quire)`: `quire-howto.md` "Pick or add an agent", `quire.md` §4.1 and §6, and `BUILD.md`.

The image changes (AOSP: Quire core, the Terminal app, the manifest; the guest image: `quired` and its units). The
release that carries it takes the PR and its checks. The guest image and its sources are published only with that
release's approval, after B Honey approves the licensing request in §7.

## 10. Not in this design

- Pairing a second computer (`quire-pairing.md`).
- Direct cloud APIs with no CLI (`quire.md` §4, connector 3).
- An adapter for Codex: it appears under "Coming to Quire" until `quired` can run it.
- Translations: English only, as in OpenBook setup.
