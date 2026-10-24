# JARVIS on the Windows half

Short answer: **yes, and most of it is already portable.** The engine — the
service, the toolbox, the archetypes, the figure genome, the compiler, the
author, the MCP server — is stdlib plus `pyyaml` and `requests`, and runs
unchanged. Everything that was not portable lived in one layer: the thing that
puts a command on PATH and starts something at login.

    python cli.py link       writes %LOCALAPPDATA%\Programs\jarvis\jarvis.cmd
    jarvis install           writes a Startup entry, so it runs at login
    jarvis doctor            checks the Windows chain, not the Linux one
    jarvis app               opens the window

## What changes, and why

| | Linux | Windows |
|---|---|---|
| the command | `~/.local/bin/jarvis` (bash) | `%LOCALAPPDATA%\Programs\jarvis\jarvis.cmd` |
| runs at login | a systemd user unit | a `.cmd` in the Startup folder |
| the window | `jarvis-window` (bash) → Chromium | `jarvis-window.cmd` → Chrome or Edge |
| pinning the companion | a KWin rule | PowerToys **Always on Top** (Win+Ctrl+T) |

A Startup `.cmd` is the honest equivalent of a user unit: it runs at login, it
needs no admin, and it needs nothing installed. It does not restart on failure
the way systemd does — if that starts to matter, that is the moment to reach
for a service wrapper, not before.

Windows 10 and later ship `curl.exe`, so the window launcher checks whether the
service is up with no extra dependency, and starts it if not — same rule as the
Linux side: **clicking an icon should start the app, not send you to a
terminal.**

## What does not come across

- **Voice, presence and gestures.** openWakeWord, Piper and the MediaPipe
  pipeline are all Linux-side here. They are not impossible on Windows, but
  nothing about them has been tried, and claiming otherwise would be guessing.
- **The sensors.** `rocm-smi`, `systemctl --failed` and the PipeWire players
  are Linux programs. The watchers already run through shims with pure parsers,
  so they return nothing rather than crashing — but the proactive daemon has
  less to say on Windows.
- **Always-on-top.** Windows has no KWin rules. PowerToys does it with a
  keystroke and is the least-worst answer; a native pinned window would mean
  writing one, which is a real project rather than a config file.

## The part that is actually interesting: it is one machine

Dual boot means only one side runs at a time, so this is two installs of one
thing rather than a cluster. What matters is which state follows you across a
reboot.

**Already shared, because it is in git:** the archetypes, the figure genomes,
the compiled figures, the docs, every bit of code.

**Not shared, and worth thinking about:** `config/jarvis.env`, the notes file,
`~/.local/state/jarvis/token` (which should *not* be shared — it is minted per
start), and the Ollama model blobs, which are tens of gigabytes and would be
downloaded twice.

Ollama's model store can be pointed at a path, so if the two installs share an
NTFS data partition the weights can be downloaded once. Linux reads NTFS
natively; Windows cannot read ext4 without extra software, so a shared NTFS
volume is the direction that works.

## And the SolidWorks thread

There is already a reason for JARVIS to exist on the Windows side:
`bridges/manifest.yaml` declares a SolidWorks bridge that must run where
SolidWorks does. Two possible shapes, and they are genuinely different:

1. **Windows runs its own JARVIS.** Simple, and each half is self-contained.
2. **Windows runs only the bridge**, and the Linux JARVIS reaches it over the
   tailnet — which is what the manifest already assumes, and what the suite doc
   described from the start.

They are not exclusive: the bridge is an MCP server either way, and whichever
JARVIS is awake can mount it. The second is the one already designed for; the
first is what this document makes possible.
