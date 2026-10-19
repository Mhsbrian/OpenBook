# Quire on your laptop: a short how-to

For the G14 after ANAL-225's update (`openbook-ota-20261019-quire2`). How it works is in [`quire.md`](quire.md).

## Call Quire

- **Shake the pointer** quickly from side to side, or press **Meta+Space**; the assist key works too. The note opens
  next to the pointer.
- Type and press **Enter**. **Esc** stops an answer that is running, and closes the note when nothing runs.
- **Meta+Space again** hides a running task in the taskbar. It keeps running, and the same key brings it back.
- Over **Settings, Files and the permission screens** the note stays hidden: those screens hide floating windows on
  top of them. Whether Quire should move into the assistant's own window so it shows there too is still your call.

## Ask it to do things (since ANAL-220)

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

**Undo:** every setting Quire changes is listed in the note with an undo button; or say "undo that".

**The first time** the agent reads your screen, the laptop asks "Allow Quire to use screen and app data?"; and the
first time it works in an app, it asks whether Quire may use screen automation there. Battery Saver can't turn on while
the laptop is plugged in.

## Pick or add an agent

- **The first time**, the note says "Connect an agent" and lists what it found in the Linux environment, such as
  **opencode**. Click **Connect opencode**. Quire sends nothing to an agent before you connect it.
- **To switch agents**, click the agent's name at the top of the note.
- **To add an agent**, install its command-line tool in the Linux environment: open **Terminal** and install it
  the way its maker says. The next time you call Quire, the note lists it. Quire knows Claude Code, opencode,
  GitHub Copilot CLI, Cursor Agent, Gemini CLI, Codex CLI, Grok CLI, Antigravity CLI, Kimi Code, Hermes and Oh My Pi.
- **Sign-ins:** an agent that needs one shows **Sign in** in the note. The agent runs its own sign-in, and Quire never
  sees your password. None of your accounts were copied to the laptop. The opencode that comes installed uses its free
  model, with no account.

## The Linux environment

- **First start:** turn on **Settings › System › Developer options › Linux development environment**, then open
  **Terminal** once. It installs OpenBook's Debian image, with `quired` and opencode, from `/sdcard/linux/` and starts
  it (on the G14 since 2026-10-19 10:39Z; elsewhere, `scripts/quire/linux-env-adb.sh push` puts it there). Without it,
  the Terminal app downloads Google's image, which has no `quired`, so Quire finds no agent.
- **To stop it for now:** use the Terminal notification.
- **To turn it off:** switch **Linux development environment** off. Quire then says the Linux environment is off
  instead of failing.
- **To remove it with its files:** Terminal › Settings › Recovery.

## Roll back

- **Before you restart:** the update just waits. Ask me and I cancel it (`g14-adb.sh ota-cancel`); slot B stays as it
  was.
- **If the new system doesn't start:** the laptop tries it three times, then starts the previous system by itself,
  with your data. Holding the power button for 10 s forces each retry. To choose by hand, hold a key at power-on and
  pick "OpenBook (17 · slot B)".
- **Once the new system has started:** it is marked good and the old one is replaced. Going back then means sending
  the old build as a new update: about 40 minutes to build, 2 to install.
