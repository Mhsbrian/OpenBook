# Quire on your laptop: a short how-to

Quire is OpenBook's assistant. It works with the AI agents you already use, and lets them do things on the laptop for
you. This page covers using it. How it works is in [`quire.md`](quire.md).

## Call Quire

- **Shake the pointer** quickly from side to side, or press **Meta+Space**; the assist key works too. The note opens
  next to the pointer.
- Type and press **Enter**. **Esc** stops an answer that is running, and closes the note when nothing runs.
- **Meta+Space again** hides a running task in the taskbar. It keeps running, and the same key brings it back.
- **Over Settings, Files and the permission screens** the note stays hidden, because those screens hide floating
  windows on top of them. It does show there while it asks you a question. Whether the note should show there all the
  time is still an open decision (`quire.md` §8 item 10).

## Ask it to do things

Say it the way you would to a person. The agent knows it is Quire on this laptop, and does it:

- "open Chrome and go to Fox News", "open Files and show my Downloads", "open Calculator"
- "turn on dark theme", "make the text bigger", "turn on Battery Saver", "turn the volume down", "turn off Bluetooth"
- "what's on my screen?", "summarise this page"
- "in Settings, find Bluetooth and turn it off": the app opens in the note's live view, where you can Pause, Take
  over or Stop.
- "move this window to the left", "close Calculator", "what's on my clipboard?", "pause the music"

**What asks you first:** anything destructive. The note shows exactly what will happen, with **Allow** and
**Don't allow**: deleting or replacing a file, developer and adb settings, and in an app any button that deletes,
uninstalls, sends, pays or buys. Don't allow means nothing happens.

**Undo:** every setting Quire changes is listed in the note with an undo button, for 24 hours; or say "undo that".

**The first time** the agent reads your screen, the laptop asks "Allow Quire to use screen and app data?". The first
time it works in an app, the laptop asks whether Quire may use screen automation there.

Battery Saver can't turn on while the laptop is plugged in. Android allows it only on battery.

## Pick or add an agent

- **The first time**, the note says "Connect an agent" and lists what it found in the Linux environment. Click
  the **Connect** button for the agent you want. Quire sends nothing to an agent before you connect it.
- **To switch agents**, click the agent's name on the note's last line.
- **To add an agent**, install its command-line tool in the Linux environment: open **Terminal** and install it the
  way its maker says. The next time you call Quire, the note lists it. Quire knows Claude Code, opencode, GitHub
  Copilot CLI, Cursor Agent, Gemini CLI, Codex CLI, Grok CLI, Antigravity CLI, Kimi Code, Hermes and Oh My Pi. Not all
  of them can run through Quire yet; `quire.md` §6 lists which.
- **Sign-ins:** an agent that needs one shows **Sign in** in the note. The agent runs its own sign-in, and Quire never
  sees your password. Some agents sign in only from the Terminal, with their own login command.
- Test images of the Linux environment come with opencode, which uses its free model and needs no account. A product
  image ships no agent.

## The Linux environment

Agents run in the Linux environment, a Debian virtual machine on the laptop. It needs hardware virtualization (SVM on
AMD) turned on in the laptop's firmware; without it, Quire says so.

- **First start:** turn on **Settings › System › Developer options › Linux development environment**, then open
  **Terminal** once. On a `userdebug` build, such as the developer previews, it installs OpenBook's Debian image, with
  `quired`, from `/sdcard/linux/images.tar.gz` and starts it. From a build host, `scripts/quire/linux-env-adb.sh push`
  puts the image there. Without it, the Terminal app downloads Google's image, which has no `quired`, so Quire finds no
  agent.
- **To stop it for now:** use the Terminal notification.
- **To turn it off:** switch **Linux development environment** off. Quire then says the Linux environment is off
  instead of failing.
- **To remove it with its files:** Terminal › Settings › Recovery. Do this before installing a new image: replacing
  the image deletes the guest's files.
- **Network:** cloud agents need the laptop to be online; the Linux environment uses Android's connection.

## If an update goes wrong

Quire arrives with OpenBook updates. An installed OpenBook updates its other slot and keeps your data
(`adb-debug.md` §7):

- **Before you restart,** a staged update can be cancelled (`scripts/g14-adb.sh ota-cancel` from the build host).
- **If the new system doesn't start,** the laptop tries it three times, then starts the previous system by itself,
  with your data. For a hang, holding the power button for 10 s forces the next try. To choose by hand, hold a key at
  power-on and pick the other "OpenBook (17 · slot …)" entry.
- **Once the new system has started,** it is marked good and the old one is replaced. Going back then means
  installing the old build as a new update.
