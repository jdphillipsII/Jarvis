#!/usr/bin/env python3
"""Camera -> presence intents. The only hardware in the presence chain.

Everything that decides anything lives in core/presence.py and is tested
without a camera. This file is a loop: grab a frame, ask the detector, hand
the boolean to the tracker, publish what comes back.

Runs at ~2 fps on purpose. Presence changes on the scale of minutes, and the
CPU belongs to the gesture pipeline and Whisper.

    python vision/presence_daemon.py                 # local webcam
    JARVIS_CAM=http://192.168.1.42:8080/video python vision/presence_daemon.py
"""
from __future__ import annotations

import argparse, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.bus import send
from core.config import cfg
from core.intent import Intent
from core.presence import PresenceConfig, PresenceEventType, PresenceTracker

POLL_HZ = 2.0
DEFAULT_SOCKET = f"/run/user/{os.getuid()}/jarvis.sock"



def _require_vision() -> None:
    """Fail with the fix, not a traceback."""
    missing = []
    for mod, pkg in (("cv2", "opencv-python"), ("mediapipe", "mediapipe")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        sys.exit(f"missing: {', '.join(missing)}\n"
                 f"  uv pip install {' '.join(missing)}\n"
                 f"  (or: bash setup/install.sh)")

def open_camera(spec: str):
    import cv2
    cap = cv2.VideoCapture(int(spec) if spec.isdigit() else spec)
    if not cap.isOpened():
        sys.exit(f"cannot open camera {spec!r}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def make_detector(min_confidence: float = 0.5):
    """MediaPipe face detection. Model 1 is the full-range model — better when
    you're leaning back from the desk than the close-range default."""
    import cv2
    import mediapipe as mp
    fd = mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=min_confidence)

    def detect(frame) -> bool:
        result = fd.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        return bool(result.detections)
    return detect


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=cfg("JARVIS_SOCKET", DEFAULT_SOCKET))
    ap.add_argument("--camera", default=cfg("JARVIS_CAM", "0"))
    ap.add_argument("--confidence", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true",
                    help="print transitions instead of publishing")
    args = ap.parse_args()
    _require_vision()

    cap = open_camera(args.camera)
    detect = make_detector(args.confidence)
    tracker = PresenceTracker(PresenceConfig())
    period = 1.0 / POLL_HZ
    print(f"presence: camera={args.camera} -> {args.socket}  (ctrl-c to stop)")

    try:
        while True:
            started = time.monotonic()
            ok, frame = cap.read()
            # A dropped frame is not evidence of absence; the grace window
            # absorbs it either way, but don't feed a false negative.
            event = tracker.feed(bool(ok) and detect(frame)) if ok else None

            if event:
                name = ("presence.arrived" if event.type is PresenceEventType.ARRIVED
                        else "presence.left")
                intent = Intent(name, source="presence", confidence=0.9, args={
                    "away_seconds" if event.type is PresenceEventType.ARRIVED
                    else "present_seconds": round(event.seconds, 1),
                    "should_greet": event.should_greet,
                })
                print(f"  {name}  ({event.seconds:.0f}s, greet={event.should_greet})")
                if not args.dry_run:
                    try:
                        send(args.socket, intent)
                    except OSError as exc:
                        print(f"  [bus unreachable: {exc}]")

            time.sleep(max(0.0, period - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
