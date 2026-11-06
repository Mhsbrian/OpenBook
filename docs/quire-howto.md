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

## Set up Quire

Open **Quire** from All Apps, or click **Set up Quire** in the note. Setup is one window with four steps, and a step
that is already done is skipped:

1. **Linux:** Quire turns on the Linux environment, downloads it (about 800 MB, once), checks it and starts it. You
   can close the window; a notification says when it's ready. If the laptop's virtualization is off in its
   firmware, the page says how to turn it on.
2. **Agents:** pick the ones you want. Each card says who makes it and what it needs: opencode works with free
   models and needs no account. **What will run** shows the exact commands before you install. Agents run as your
   user in the Linux environment, without admin rights.
3. **Sign in:** each agent signs in with its maker, in your browser. The window shows a one-time code to copy, or a
   field for the code the page gives you. Some agents take an API key instead. Quire never sees your password.
4. **Try it:** Quire sends one real request to your default agent and shows the answer.

After setup, **Quire** in All Apps opens on your agents: the Linux environment (Stop, Start), and each agent with
Update, Sign in again, Sign out and Remove, a mark for the default one, and **Add agents**. Terminal is still there
for anything else: any agent that speaks the Agent Client Protocol and is on the Linux environment's `PATH` is listed.

- **To switch agents**, click the agent's name on the note's last line.
- **Quire knows** Claude Code, opencode, GitHub Copilot CLI, Cursor Agent, Gemini CLI, Antigravity CLI, Kimi Code,
  Grok CLI, Hermes and Oh My Pi. Codex CLI is listed as coming. `quire-setup.md` §5 has each one's installer and
  sign-in.
- **Keys** are kept only in the Linux environment, in a file only your user can read. Other agents there run as
  your user too, so they could read it. Sign out deletes it.
- **Test images** of the Linux environment come with opencode. A release image ships no agent.

## The Linux environment

Agents run in the Linux environment, a Debian virtual machine on the laptop. It needs hardware virtualization (SVM on
AMD) turned on in the laptop's firmware; without it, Quire says so.

- **First start:** Quire setup does it (above). The image is OpenBook's own Debian image with `quired`, checked
  against a SHA-256 the build pins. On a `userdebug` build, such as the developer previews, a copy at
  `/sdcard/linux/images.tar.gz` is used instead; from a build host, `scripts/quire/linux-env-adb.sh push` puts it
  there. A build that names no image says so; OpenBook never installs Google's image, which has no `quired`.
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
