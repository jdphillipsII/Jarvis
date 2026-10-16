# Where JARVIS lives

    python3 ~/jarvis/cli.py link            once: puts `jarvis` on PATH
    jarvis install                          units, desktop entries, the rest
    systemctl --user enable --now jarvis    the one process
    jarvis app                              the application window
    jarvis companion                        the small window that follows you

The first line is the bootstrap and only needs running once. `jarvis` is a
four-line launcher in `~/.local/bin` that resolves the venv at run time and
execs this checkout's `cli.py`, so creating the audio venv later does not
require regenerating it, and moving the checkout means re-running `link`.

---

## The daemon had to come first

The obvious move was to build a window. It would not have worked, for a reason
that is easy to miss until something breaks:

**A proposal is state.** `ProposalStore` lives in memory, and until now every
command built its own JARVIS — `jarvis chat` had a toolbox, `jarvis watch` had
another, the MCP server a third. So a proposal raised by voice could not be
confirmed from a window, because they were different processes holding
different stores. The consent model promises that *"re-confirming is
idempotent — a second confirm from voice and the HUD at once returns the
original result rather than running it twice"*, and three separate processes
cannot keep that promise.

So `daemon/service.py` is one JARVIS holding the bus, the registry, the
toolbox and its proposals, the HUD state and the agent. Everything else is a
client: the CLI, both windows, the voice loop, MCP.

There is a test for exactly the thing that was broken — one surface raises a
proposal, a second surface with no memory of the first lists it and confirms
it, the work happens, and confirming again from the first does not repeat it.

`jarvis status` now answers from the warm process and reports its uptime, which
is also how you can tell which one you are talking to.

### What the API will not do

`POST /api/agency` is implemented and always refuses. Raising the ceiling is a
deliberate act by the user at the machine, not something a surface can ask for
— least of all one reachable over a socket.

### Reading is open on loopback; acting is not

A token is minted at each start, written `0600` to
`~/.local/state/jarvis/token`, and required on everything that mutates. Showing
state to anything on loopback is fine. Confirming a proposal that may reach a
shell is not: any local process can open a socket, and not every local process
should be able to execute a pending command. A wrong token and a missing token
return the same words, so probing for the difference tells you nothing.

The served page carries the token inline, because the process that mints it is
the process that serves the page.

---

## Two windows, one page

Both front ends are the same served app. They differ only in window class,
which is what KWin's rules key off — one codebase, two behaviours.

**No Electron and no Tauri.** The page is already served on loopback, so a
browser in app mode is a real window with its own icon, its own taskbar entry
and no second runtime to install, update or ship a CVE. If the pinned window
turns out not to be enough, a Plasma widget is a later addition rather than a
prerequisite.

| | class | shape |
|---|---|---|
| `jarvis app` | `jarvis` | a normal 1280×860 application window |
| `jarvis companion` | `jarvis-companion` | 460×720, pinned, no titlebar, every desktop |

`jarvis install` writes both `.desktop` entries with this checkout's path baked
in, so they appear in the launcher like any other app.

### Making the companion actually follow you

The small window needs one KWin rule, imported once:

> System Settings → Window Management → Window Rules → **Import**
> `setup/app/jarvis-companion.kwinrule`

It sets: above everything including full-screen work, absent from the taskbar,
the task switcher and the pager (it is furniture, not a task), present on every
desktop and activity, no decoration since the page draws its own frame, and
**never steals focus** — `fsplevel=4`, because a companion that grabs the
keyboard while you are typing is not a companion.

Then bind a global shortcut to:

    <checkout>/setup/app/jarvis-window companion

### Wayland, honestly

On Plasma 6 under Wayland a client cannot simply declare itself always-on-top;
that decision belongs to the compositor. The KWin rule is how you tell the
compositor, and it is the supported path rather than a workaround. A
layer-shell overlay would be more native still, but it needs a new dependency
and a toolchain, and this needs neither.

**I have not been able to run either window.** This machine has no display and
no KDE, so the daemon, the API and the client are tested and the two windows
are not. The launcher checks the daemon is up and says what to do if it is not;
beyond that, the first run is the test.

---

## What is still missing

- The page served at `/` is the existing HUD, which was built for the
  proactive daemon's feed. It does not yet show the toolbox, the figures, the
  archetypes or a place to type. That is the next piece of work, and it is now
  a front-end job rather than an architectural one.
- The voice loop and the gesture daemon still build their own toolboxes. They
  should become clients too, which is the same change `jarvis status` just had.
- No icon of our own; the `.desktop` entries borrow a stock one.
