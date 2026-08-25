#!/usr/bin/env python3
"""Camera -> gestures -> intents. The only hardware in the gesture chain.

Everything that decides anything is in core/gestures.py and core/debounce.py
and is tested without a camera. This is a loop: read a frame, get landmarks,
classify, debounce, publish.

MediaPipe runs on CPU deliberately — your 12900K handles it at ~10% of a few
cores, and every megabyte of VRAM belongs to the model.

    python vision/gesture_daemon.py --dry-run          # print, don't publish
    JARVIS_CAM=http://PHONE_IP:8080/video python vision/gesture_daemon.py
    python vision/gesture_daemon.py --preview          # draw landmarks in a window
"""
from __future__ import annotations

import argparse, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.bus import send
from core.config import cfg
from core.debounce import Debouncer
from core.gestures import DragTracker, Gesture, GESTURE_INTENTS, classify
from core.intent import Intent

FPS = 30
ORBIT_GAIN = 2.5            # normalised hand movement -> orbit radians-ish
ORBIT_MIN = 0.004           # ignore tremor
DEFAULT_SOCKET = f"/run/user/{os.getuid()}/jarvis.sock"


def open_camera(spec: str):
    import cv2
    cap = cv2.VideoCapture(int(spec) if spec.isdigit() else spec)
    if not cap.isOpened():
        sys.exit(f"cannot open camera {spec!r}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def make_tracker(confidence: float):
    import cv2
    import mediapipe as mp
    hands = mp.solutions.hands.Hands(
        max_num_hands=1, model_complexity=0,       # 0: fast, plenty for poses
        min_detection_confidence=confidence, min_tracking_confidence=confidence)

    def landmarks(frame):
        res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not res.multi_hand_landmarks:
            return None
        return [(p.x, p.y) for p in res.multi_hand_landmarks[0].landmark]
    return landmarks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=cfg("JARVIS_SOCKET", DEFAULT_SOCKET))
    ap.add_argument("--camera", default=cfg("JARVIS_CAM", "0"))
    ap.add_argument("--confidence", type=float, default=0.6)
    ap.add_argument("--stable-frames", type=int, default=4)
    ap.add_argument("--cooldown", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--preview", action="store_true", help="show the camera view")
    args = ap.parse_args()

    cap = open_camera(args.camera)
    landmarks = make_tracker(args.confidence)
    deb = Debouncer(stable_frames=args.stable_frames, cooldown_s=args.cooldown)
    drag = DragTracker()
    dragging = False
    period = 1.0 / FPS

    def publish(name: str, args_: dict, conf: float) -> None:
        if args.dry_run:
            return
        try:
            send(args.socket, Intent(name, source="gesture",
                                     confidence=round(conf, 3), args=args_))
        except OSError as exc:
            print(f"  [bus unreachable: {exc}]")

    print(f"gestures: camera={args.camera} -> {args.socket}  (ctrl-c to stop)")
    print("  open palm=dismiss  fist=mute  point=focus  peace=next  pinch+move=orbit")
    try:
        while True:
            started = time.monotonic()
            ok, frame = cap.read()
            if not ok:
                continue
            reading = classify(landmarks(frame))

            # Pinch is continuous: a held drag streams orbit deltas rather
            # than firing once. It bypasses the debouncer entirely.
            if reading.gesture is Gesture.PINCH:
                if not dragging:
                    drag.start(reading); dragging = True
                    deb.reset()
                    print("  [pinch] drag start")
                else:
                    dx, dy = drag.delta(reading)
                    if abs(dx) > ORBIT_MIN or abs(dy) > ORBIT_MIN:
                        publish("model.orbit",
                                {"dx": round(dx * ORBIT_GAIN, 4),
                                 "dy": round(dy * ORBIT_GAIN, 4)},
                                reading.confidence)
            else:
                if dragging:
                    drag.stop(); dragging = False
                    print("  [pinch] drag end")
                fired = deb.feed(reading.gesture.value if reading.gesture else None)
                if fired:
                    name = GESTURE_INTENTS[Gesture(fired)]
                    print(f"  {fired} -> {name}  ({reading.confidence:.2f})")
                    publish(name, {}, reading.confidence)

            if args.preview:
                import cv2
                label = reading.gesture.value if reading.gesture else "-"
                cv2.putText(frame, label, (12, 36), cv2.FONT_HERSHEY_SIMPLEX,
                            1.0, (255, 220, 0), 2)
                cv2.imshow("jarvis gestures", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            time.sleep(max(0.0, period - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
