# What we take from Axon, and what we leave

A scan of the Axon codebase (enterprise multi-tenant "intelligence OS") for
patterns worth reusing in a single-user desktop assistant. Verdicts are blunt
on purpose: most of that repo is the right idea wrapped in tenancy scaffolding.

## Taken

| From | What | Landed in |
|---|---|---|
| `vad_service.py` | POST_SPEECH end-of-speech state machine | `core/endpointing.py` |
| `internal_event_bus.py` | hierarchical `group.*` patterns, snapshot-then-call, error counting | `core/bus.py` |
| `ews/registry.py` + engine:1050 | decorator registry, try/except in the *dispatcher* | pending |
| `voice_proactive.py` | the offer handshake (below) | pending |
| `temporal_awareness.py` | severity ladder + DeliveryContext-as-one-argument | pending |
| `aria_user_calibration.py:235` | 168-bucket hour-of-week quiet-hour learning | pending |
| `focus_context_resolver.py` | window-title -> typed entity extraction | pending |
| `sycophancy_guard.py` | framing-bias detection + conditional prompt block | pending |

## Rejected

| From | Lines | Why |
|---|---|---|
| `org_runtime_kernel.py` | 2901 | Multi-tenant context assembly. Take `_safe_block`'s per-source timeout budget (~30 lines) and the `RuntimeBlock` data+rendered dual representation; leave the rest. |
| `aria_action_orchestrator` body | 2013 | Multi-approver policy escalation is meaningless with one user. Keep only: proposals expire as a *state* not an error; re-confirming returns the prior result; the confirm entry point never raises. |
| `kernel_adapters.py` | 602 | Ten classes of field-copying with no shared protocol. A function per surface is the same thing, shorter. |
| `SprintPhase` in `temporal_awareness` | ~40 | Scrum modelling. Replace with "is the user focused right now", which is the signal that actually matters. |
| `command_palette.py` | 802 | Same catalog idea as the orchestrator, 15 SQLAlchemy models deep. Take the 9-line `PaletteActionDef` shape. |

## The design correction worth reading twice

`voice_proactive.py` states: **no severity level unlocks auto-speak.** Even
critical events emit an offer and wait to be accepted before any TTS runs.

This contradicts `temporal_awareness.should_surface`, where `critical` returns
True unconditionally. Both files are in the same repo; the voice one is right,
because a speaker in a room at 2am is not a dashboard. JARVIS adopts the
offer handshake: proactive speech is always an offer, never an announcement.

Corollary taken from the same file: the shut-up command is matched by a
deliberately *literal* regex (`pause|not now|shush|hold on|quiet|hush`,
standalone utterance, <= 40 chars) with no fuzzy intent detection, so that
"hold on, let me check that" mid-sentence cannot silence the assistant.

## Honest caveat

`sycophancy_guard.py` is not persona enforcement. It corrects one specific
failure - answering "why is X a good idea" with three strengths and "why is X
a bad idea" with three weaknesses. Nothing in Axon enforces a consistent voice.
JARVIS's dryness is ours to write.
