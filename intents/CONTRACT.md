# Intent bus contract

One message shape. Sources publish, actuators subscribe. This is the keystone:
retrain gestures, add a foot pedal, or let voice fire the same action — all
without touching any actuator.

## Message (JSON, one per line)

    {
      "intent":     "workspace.next",   // namespaced verb, see registry.yaml
      "source":     "gesture",          // gesture | voice | presence | system
      "confidence": 0.92,               // 0..1
      "args":       {},                 // intent-specific payload
      "ts":         1717000000.0        // epoch seconds
    }

## Rules

- Actuators ignore any intent not in `registry.yaml` (fail closed).
- Actuators enforce the per-intent confidence floor.
- Debounce at the SOURCE, not the actuator — one twitchy frame must not fire.
- `source` is advisory only; never trust it for authorization.
