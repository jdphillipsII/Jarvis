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

---

## The walkthrough

Everything below is in a normal Command Prompt unless it says PowerShell.

### 1. The two prerequisites

```
winget install Git.Git
winget install Python.Python.3.12
```

**Not the Microsoft Store Python.** It redirects `%LOCALAPPDATA%` writes into a
per-app sandbox, which is exactly where the launcher and the token go.
`pyproject.toml` pins `>=3.11,<3.13`, so 3.12 is the one to take.

Close the terminal and open a new one, so both land on PATH.

### 2. Clone

```
git clone https://github.com/jdphillipsII/Jarvis.git %USERPROFILE%\jarvis
cd %USERPROFILE%\jarvis
```

### 3. The environment

`setup/install.sh` is bash and will not run here, so this is it by hand. The
path matters: the launcher looks for the venv at exactly `.venvs\voice`.

```
py -3.12 -m venv .venvs\voice
.venvs\voice\Scripts\python -m pip install --upgrade pip
.venvs\voice\Scripts\pip install pyyaml requests numpy CoolProp
```

`pyyaml` and `requests` are what the service cannot start without. `numpy` and
`CoolProp` are for the figure work and can wait if a wheel gives trouble.

### 4. Put `jarvis` on PATH

```
.venvs\voice\Scripts\python cli.py link
```

It prints a PowerShell line to add the directory to your PATH. Run that in
**PowerShell**, then open a new terminal.

> Do not use `setx PATH "%PATH%;..."`. `%PATH%` in a running shell is the
> system and user paths already joined, so that writes the whole thing back
> into the *user* variable — duplicating the system half and truncating at
> 1024 characters. It is the classic way to lose your PATH.

Check it took: `jarvis doctor`

### 5. Your config

`config/jarvis.env` is gitignored, so Windows has only the example. The code
falls back to the example, but you want your own:

```
copy config\jarvis.env.example config\jarvis.env
notepad config\jarvis.env
```

With one model doing everything, set it as the fast model and **leave the
heavy one empty** — escalating from a model to itself is a round trip for
nothing:

```
JARVIS_CHAT_MODEL=qwen3.5:35b-a3b
JARVIS_HEAVY_MODEL=
```

### 6. The model

```
winget install Ollama.Ollama
ollama pull qwen3.5:35b-a3b
```

22 GB against 24 GB of VRAM, so the desktop's share may push a few layers into
RAM. With 3B active per token that is tolerable rather than painful. If it
drags, `qwen3.5:35b-a3b-int4` is 20 GB and `qwen3.8:27b` is 18 GB.

Confirm the card is being used: `ollama ps` should show a GPU percentage after
the first prompt.

### 7. Install and run

```
jarvis install
jarvis doctor
jarvis app
```

`jarvis install` writes the Startup entry, so from the next login it is simply
there. `jarvis app` starts the service if it is not already up.

### 8. The companion window

```
winget install Microsoft.PowerToys
jarvis companion
```

Focus the small window and press **Win+Ctrl+T** to pin it. There is no KWin
here, and a natively pinned window would mean writing one.

---

## When it does not work

| what you see | what it is |
|---|---|
| `'jarvis' is not recognized` | step 4, or the terminal predates the PATH change |
| service exits immediately | run `jarvis serve` in the foreground — it prints the reason |
| `127.0.0.1:8787 is already in use` | something else holds it; `jarvis serve --port 8790` |
| `ModuleNotFoundError: yaml` | step 3 went into the wrong Python. `jarvis doctor` checks the one the launcher picks |
| the model answers from the CPU | `ollama ps`; if it shows 100% CPU the layers did not fit — take a smaller tag |

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
