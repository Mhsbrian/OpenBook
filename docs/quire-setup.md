# Quire setup: agents in a few clicks (ANAL-393)

As of 2026-11-06. This is the design and the build plan for setting up Quire's agents: a short wizard that gets the
Linux environment ready, installs the agents a person picks, signs them in and checks that one answers. After setup,
the same window is where agents are managed. It is for review before it is built. How Quire works is
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
  - **The Terminal app** installs OpenBook's own guest image on every build type, checked against a SHA-256 pinned
    in the system image, and reports progress.
  - **`quired`** learns to install, update and remove agents and to run their sign-in, and Quire core keeps the
    guest's `quired` up to date without replacing the guest.
  - **Quire core** gets the wizard and the agents page. The note's "no agent" card opens the wizard.
- **Needs B Honey once (§7):** publishing OpenBook's guest image (Debian 13 and `quired`, about 790 MB) as a release
  asset, with the Debian source it requires. Until then, previews keep sideloading the image over adb, and a `user`
  build says plainly that it has no Linux environment image.
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
| 2 | **Agents** | Selects cards, then Install | Lists `quired`'s catalog. Each card shows the maker and what the agent needs ("Free models, no account", "A GitHub account with Copilot"). Installed agents show their version. Agents Quire can't run yet (Codex today) are named under the grid, not offered. opencode is marked "Good first pick": it needs no account. | `agents` |
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

- **Source order** in `ImageArchive.from`:
  1. a debuggable build's `/sdcard/linux/images.tar.gz`, as today, for the checks;
  2. **OpenBook's image**, named by `/product/etc/openbook/linux-env.json` in the system image: its URL, SHA-256, size
     and version. The archive is hashed as it streams and checked before the install is committed (the marker file
     is written only after the hash matches). A mismatch deletes the partial install and reports `error` with the
     reason;
  3. Google's image only when that file is absent, which never happens in an OpenBook product. AOSP's behaviour stays
     for anyone else.
- **Resume:** `ImageArchive` already supports HTTP ranges. A download that drops resumes on the next start.
- **Progress through the bridge:** `status` and `start` also return `phase` (`download`, `unpack`, `start`), `bytes`
  and `total`, and `stop` is added. The wizard reads these and invents nothing.
- **Why pinned:** AOSP allows `/sdcard` only on debuggable builds because any app can write there. A hash pinned in
  the read-only system image keeps that guarantee on `user` builds and covers the download too.

### 4.2 `quired`: install, sign-in and update (`quire/quired/internal/setup/`)

New ACP extension methods next to `_quire/agents` and `_quire/describe`, so it is the same connection over vsock:

| Method | What it does |
|---|---|
| `_quire/catalog` | Every catalog agent: name, maker, what it needs, whether Quire can run it, whether it is installed (path, version), its sign-in kinds |
| `_quire/install {agent}` | Runs the agent's recipe (§5) as `droid`, in its own process group, with a deadline. Progress arrives as `_quire/progress` notifications (step, bytes when known, the last output line). Ends with the version found, or the failing step and its output |
| `_quire/update {agent}`, `_quire/remove {agent}` | The same, with the maker's update or uninstall method |
| `_quire/login {agent, method}` | Runs the agent's own login command on a pseudo-terminal. `quired` reads its output and sends `_quire/login/prompt` with what it found: a URL to open, a device code, or "paste a code". The full output is in Details. It ends when the command exits, then checks the sign-in state |
| `_quire/login/input {text}` | Writes the pasted code to the login's terminal. It isn't logged, and isn't kept after the write |
| `_quire/signin {agent}` | Whether the agent is signed in, by its own status command where it has one, else by a no-prompt `session/new` |
| `_quire/cancel {job}` | Cancels a running install or login: SIGTERM to its process group, then SIGKILL 3 s later, as for agents (`quire.md` §6) |
| `_quire/self-update {deb, sha256}` | Installs a newer `quired` package that Quire core sends (§4.3), after checking it against the hash the core pinned, then restarts the service. The connection drops and Quire reconnects |

- **Recipes live in the catalog**, next to the version each one was last checked against, with the source URL and date
  of the maker's instructions. A recipe is a list of steps: Debian packages (`sudo apt-get install -y …`, the only
  step that uses `sudo`), an npm package (`npm install -g --prefix ~/.local …`), a uv tool, or the maker's install
  script fetched over HTTPS and run with `bash`. Each step's command is shown in Details before and while it runs.
- **PATH:** installs go to `~/.local`. `quired.service` adds `~/.local/bin` and the makers' own folders to the
  agents' `PATH`, so a new agent is found without a restart.
- **The pseudo-terminal** uses only the standard library (`/dev/ptmx` with `TIOCSPTLCK` and `TIOCGPTN`), as `quired`
  already does for vsock.
- **Logs:** each job writes `~/.local/state/quire/jobs/<agent>-<time>.log` in the guest. Pasted codes and keys never
  reach a log: input written to a login's terminal is masked in the log, and the agent's own echo is cut from the
  output Quire shows.

### 4.3 Quire core

- **`setup/`:** `SetupActivity` (the window), `SetupModel` (a state machine for the pages, kept across the restarts
  the framework does, as OpenBook setup's ViewModel does), and `AgentsPage`. Built with Quire's own `ui/` (palette,
  motion, widgets), so it looks like the note without a second toolkit.
- **The guest's `quired` stays current:** Quire core carries the `quired` package that matches it, as a raw resource
  with its SHA-256. On each connection it compares versions (`initialize`'s `agentInfo.version`) and, when the guest's
  is older, sends `_quire/self-update`. A guest whose `quired` predates self-update (0.3.0 on the G14 today) can't
  receive it. For that one case the wizard offers Reinstall the Linux environment and says it deletes the guest's
  files, or the developer path, `scripts/quire/linux-env-adb.sh`.
- **The note:** the no-agent card's button becomes **Set up Quire**; "It hasn't found one yet" becomes "Set up Quire
  to choose and install an agent". The terminal-only sign-in path opens the wizard's sheet.
- **A notification** "The Linux environment is ready" (or the reason it stopped), when the window was closed during
  step 1.
- **OpenBook setup:** the Extras page gets the Quire card (§2.1). A flag in Quire's preferences opens the wizard once
  on the first desktop.

### 4.4 What doesn't change

The broker, the OS tools, the consent rules and the note's states (`quire.md` §4.2, §10; `quire-design.md` §3) stay
as they are. Pairing a second computer stays a design under review.

## 5. The agents: install and sign-in

From the makers' documentation and the CLIs' own `--help`, checked 2026-11-06 (R, or "local" for `--help` of the
version named in `quired`'s catalog on our dev host). Nothing here was installed or signed in for this design. The
recipes are checked again in the guest when they're built (§8), and the catalog records the date.

**What changed since the catalog was last checked (2026-10-18):** almost every agent now has a native installer that
needs no root and no Node.js, so only Gemini CLI needs Debian's Node.js. Grok CLI (`grok agent stdio`) and
Antigravity CLI (`agy acp`) now document ACP servers, and Gemini CLI's flag is `--acp`. **HYPOTHESIS** until
`quired probe` opens a session with each: if it does, they move from "planned adapter" to supported with no adapter
code, and only Codex stays under "Coming to Quire".

| Agent | Install (as `droid`, no root unless noted) | Update · remove | Sign-in in the wizard | Key or token | ACP |
|---|---|---|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash`, to `~/.local/bin/claude` ([setup](https://code.claude.com/docs/en/setup)) | `claude update`, or it updates itself · delete `~/.local/bin/claude` and `~/.local/share/claude` | `claude auth login`: open the URL, then paste the code the page shows back (paste-back is documented as the fallback; whether its default waits on a local port is unconfirmed) ([auth](https://code.claude.com/docs/en/authentication)) | `ANTHROPIC_API_KEY` | `quired`'s adapter (`claude.go`) |
| opencode | `curl -fsSL https://opencode.ai/v2/install \| bash` with its no-PATH-edit option, to `~/.opencode/bin`. **`opencode.ai/install` installs v1** ([v2 docs](https://opencode.ai/v2/docs)) | `opencode upgrade` · `opencode uninstall` (local 2.2.5) | None for its free models | Providers through `opencode auth login` | `opencode acp` |
| GitHub Copilot CLI | `curl -fsSL https://gh.io/copilot-install \| bash`, to `~/.local` ([install](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)) | `copilot update` · unconfirmed | `copilot login --device-code`: the code and github.com/login/device (local 1.0.106). Passed explicitly, because its default on a desktop waits on a local port | Fine-grained token in `COPILOT_GITHUB_TOKEN` | `copilot --acp` |
| Cursor Agent | `curl https://cursor.com/install -fsS \| bash`, to `~/.local/bin/cursor-agent` ([install](https://cursor.com/docs/cli/installation)) | `agent update` · not documented | `NO_OPEN_BROWSER=1 cursor-agent login` prints a link and polls; no code to copy ([auth](https://cursor.com/docs/cli/reference/authentication)) | `CURSOR_API_KEY` | `cursor-agent acp` |
| Gemini CLI | `sudo apt-get install -y nodejs npm` (Node 20 or newer; Debian 13's version is a **HYPOTHESIS** to check), then `npm install -g --prefix ~/.local @google/gemini-cli` ([install](https://www.geminicli.com/docs/get-started/installation)) | npm `@latest` · `npm uninstall -g` | `NO_BROWSER=true`: open the URL, paste the code back. Its default waits on `127.0.0.1` ([oauth2.ts](https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/core/src/code_assist/oauth2.ts)). Free-tier Google sign-in moved to Antigravity on 2026-06-18 ([auth](https://www.geminicli.com/docs/get-started/authentication)), so the card asks for a key | `GEMINI_API_KEY` | `gemini --acp` ([ACP](https://geminicli.com/docs/cli/acp-mode/)); the catalog's `--experimental-acp` is out of date |
| Antigravity CLI | `curl -fsSL https://antigravity.google/cli/install.sh \| bash`, to `~/.local/bin/agy` ([start](https://antigravity.google/docs/getting-started)) | `agy update` · unconfirmed | A Google account. It prints a URL and asks for the code back only when it detects SSH, and no flag forces that ([install](https://antigravity.google/docs/install?tab=cli)). **HYPOTHESIS** that it does so on the guest's terminal; if not, Terminal until it has a flag | `GEMINI_API_KEY` with its `modelProvider` setting | `agy acp` ([ACP](https://antigravity.google/docs/cli/acp/)) |
| Kimi Code | `curl -fsSL https://code.kimi.com/kimi-code/install.sh \| bash` with `KIMI_NO_MODIFY_PATH=1`, to `~/.kimi-code/bin` ([guide](https://moonshotai.github.io/kimi-code/en/guides/getting-started)) | `kimi upgrade` · delete the binary | `kimi login`: a device code (local 2.4.1) | `KIMI_MODEL_API_KEY` | `kimi acp` |
| Grok CLI | `curl -fsSL https://x.ai/cli/install.sh \| bash`, to `~/.grok/bin` ([docs](https://docs.x.ai/build/overview)). It also makes an `agent` link, which clashes with Cursor's: `quired` runs both by their full names | `grok update` · unconfirmed | `grok login --device-auth` (local 1.0.77) | `XAI_API_KEY` | `grok agent stdio` ([headless](https://docs.x.ai/build/cli/headless-scripting)) |
| Hermes Agent | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash`, after `git`, `curl` and `tar` from Debian. It brings its own Python and Node ([install](https://hermes-agent.nousresearch.com/docs/getting-started/installation)). ACP needs one more documented step | `hermes update` · `hermes uninstall` | Nous Portal by device code, or a provider key ([providers](https://hermes-agent.nousresearch.com/docs/integrations/providers)) | `~/.hermes/.env` (`OPENROUTER_API_KEY` and others) | `hermes acp` ([ACP](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp)) |
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

- **What runs, and where:** every install and login runs inside the guest as `droid`, never on Android. The only
  `sudo` is for Debian's own packages from Debian's archive (Node.js, npm, `curl`). The guest already gives `droid`
  passwordless `sudo` (C: AOSP's `build/debian/cloud-init_config/user-data`), and the agents already run as `droid`
  (`quire.md` §5.2), so no new privilege is involved.
- **Makers' installers:** a maker's install script is the maker's code, fetched over HTTPS from the maker's domain and
  pinned to it in the catalog. It is the same trust the person gives when installing the agent by hand, but now it
  happens on one click. So the card says who makes it, and Details shows the exact command before it runs. Ten of
  the eleven agents are installed this way today (§5); the npm packages of three of them need Node.js 22, newer than
  Debian 13's 20 (**HYPOTHESIS**), so packages are not a general alternative. **For the Checker:** is this enough, or should recipes be
  limited to packages with checksums, which would drop most agents?
- **Sign-in:** the password is typed only on the maker's page, in the browser. What passes through Quire is a one-time
  code (device-code flows: shown, not sent; paste-back flows: sent once to the login's terminal, then dropped). Quire
  core doesn't keep or log either one.
- **API keys** are only for agents whose own documented settings take one (§5). The key goes from the field to
  `quired` over vsock, into a 0600 file in the guest that `quired` reads when it starts that agent, and it is never
  logged or shown again. This is the one place a long-lived secret passes through Quire. **For the Checker:** keep it,
  or send people to Terminal for keys?
- **The image:** pinned by SHA-256 in the read-only system image (§4.1), so neither a file on `/sdcard` nor a changed
  download can replace it on a `user` build.
- **`quired` self-update:** the package comes from the system image, pinned by its hash, over the vsock connection
  that only Quire core can open (`quire.md` §5.4). The guest checks the hash before `dpkg` installs it.
- **Localhost sign-in:** a login that waits for the browser to come back to `localhost` in the guest can't finish,
  because the browser is on Android. The Terminal app would ask the person to allow forwarding of that port (C:
  `PortNotifier.kt`). The wizard uses the device-code or paste-back variant where the maker has one (§5), and
  otherwise says the agent signs in from Terminal for now.

## 7. Decisions needed

| For | Question | Recommendation |
|---|---|---|
| **B Honey** (public, licensing) | Publish OpenBook's guest image as a GitHub release asset of `Mhsbrian/OpenBook`, with the Debian source packages it contains as a second asset (GPL corresponding source), and pin its URL and SHA-256 in the build | Yes. Without it a `user` build has no agents. Alternatives: Google's image with `quired` added at first boot (depends on Google's server and terms, and a Google-built kernel), or the image inside the system image (790 MB more in each A/B slot of an 8 GiB super partition). Both are worse |
| **Checker** | Makers' install scripts on one click (§6) | Allow them, show the command, and prefer packages |
| **Checker** | API keys through Quire (§6) | Keep, with the limits in §6 |
| **Checker** | The Quire app opens the wizard or the agents page, and the test window leaves All Apps | Yes |

## 8. Tests

| Check | What it covers | Where |
|---|---|---|
| `go test -race ./...` in `quire/quired` | Recipes run step by step with the test binary standing in for `apt-get`, `npm`, `curl` and the makers' scripts. Cancel, deadline, failure output, PATH, the pseudo-terminal, URL and code detection on recorded login transcripts, masking of input, self-update hash refusal | Host, CI |
| `device/anybook/common/quire/tools/unit-test.sh` | `SetupModel`: every page transition, skip rules, the restart in the middle of a download, the copy for each `Connectors` state | Host, CI |
| `scripts/quire/linux-env-qemu.sh` with `--setup opencode` | In the real guest: install opencode by its recipe, find it, one prompt. A self-update from the previous `quired` | Host QEMU |
| `scripts/quire/setup-walk.py` (new) | The wizard in Cuttlefish: every page in light and dark, the keyboard path, the labels, Remove animations, the no-KVM page (with `initcall_blacklist=svm_init`), a pinned-hash mismatch refusing the image, opencode installed and answering | Cuttlefish |
| Release suite | One run on the G14 with a real sign-in (the owner's choice of agent) | G14, release |

Screens and logs go on the issue and in the evidence store, never in the repository.

## 9. Build order

One pull request, `feat(quire): set up agents from a wizard`, in reviewable commits:

1. `docs(quire)`: this design and its prototype.
2. `feat(quired)`: `internal/setup`, the catalog's recipes and refreshed entries (§5), the methods in §4.2, and their
   tests.
3. `feat(terminal)`: patch 0003, OpenBook's pinned image, progress and stop.
4. `feat(quire)`: the wizard, the agents page, the launcher entry, the note's card, the notification, and the
   `quired` self-update.
5. `feat(setup)`: the Quire card on OpenBook setup's Extras page.
6. `docs(quire)`: `quire-howto.md` "Pick or add an agent", `quire.md` §4.1 and §6, and `BUILD.md`.

The image changes (AOSP: Quire core, the Terminal app, the pinned guest image). The release that carries it takes the
PR and its checks. The guest image is published only after B Honey's approval (§7).

## 10. Not in this design

- Pairing a second computer (`quire-pairing.md`).
- Direct cloud APIs with no CLI (`quire.md` §4, connector 3).
- An adapter for Codex: it appears under "Coming to Quire" until `quired` can run it. Grok and Antigravity join the
  grid only if their ACP servers pass `quired probe` (§5).
- Translations: English only, as in OpenBook setup.
