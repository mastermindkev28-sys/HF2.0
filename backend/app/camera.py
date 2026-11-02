"""Camera controls.

None of the engines we run (Wan 2.2 TI2V-5B, LTX-Video 2B) take a camera path as
a native input. Camera moves are therefore *prompt-guided*: each preset is turned
into wording these models were trained to respond to. The UI says so; results
follow the instruction most of the time, not always.
"""
from __future__ import annotations

CAMERA_MOVES: dict[str, dict[str, str]] = {
    "static": {"label": "Static tripod", "text": "static locked-off tripod shot, the camera does not move"},
    "dolly_in": {"label": "Dolly in", "text": "smooth dolly-in, the camera slowly pushes forward toward the subject"},
    "dolly_out": {"label": "Dolly out", "text": "smooth dolly-out, the camera slowly pulls back away from the subject, revealing more of the scene"},
    "pan_left": {"label": "Pan left", "text": "the camera pans slowly to the left"},
    "pan_right": {"label": "Pan right", "text": "the camera pans slowly to the right"},
    "tilt_up": {"label": "Tilt up", "text": "the camera tilts slowly upward"},
    "tilt_down": {"label": "Tilt down", "text": "the camera tilts slowly downward"},
    "zoom_in": {"label": "Zoom in", "text": "slow optical zoom in on the subject"},
    "zoom_out": {"label": "Zoom out", "text": "slow optical zoom out from the subject"},
    "tracking": {"label": "Tracking shot", "text": "tracking shot, the camera moves alongside the subject keeping it in frame"},
    "orbit": {"label": "Orbit shot", "text": "orbiting shot, the camera circles around the subject in a smooth arc"},
    "crane": {"label": "Crane shot", "text": "crane shot, the camera rises smoothly upward and over the scene"},
    "fpv_drone": {"label": "FPV drone", "text": "fast FPV drone shot, swooping first-person flight through the scene"},
    "handheld": {"label": "Handheld", "text": "handheld camera with subtle natural shake, documentary feel"},
    "slow_motion": {"label": "Slow motion", "text": "slow motion, high frame rate look, every movement slowed down"},
    "cinematic_tracking": {"label": "Cinematic tracking", "text": "cinematic tracking shot on a gimbal, smooth and steady, shallow depth of field"},
    "rack_focus": {"label": "Rack focus", "text": "rack focus, the focus shifts from the foreground to the background"},
    "first_person": {"label": "First-person POV", "text": "first-person point-of-view shot, seen through the eyes of the character"},
}

INTENSITY_WORDS = {1: "very subtle", 2: "gentle", 3: "moderate", 4: "dynamic", 5: "intense, energetic"}


def camera_text(moves: list[str], intensity: int = 3) -> str:
    parts = [CAMERA_MOVES[m]["text"] for m in moves if m in CAMERA_MOVES]
    if not parts:
        return ""
    if "static" in moves:
        return CAMERA_MOVES["static"]["text"]
    word = INTENSITY_WORDS.get(int(intensity), "moderate")
    return f"{', '.join(parts)}; {word} camera motion"


def motion_text(intensity: int) -> str:
    """Subject-motion strength for image-to-video (prompt-guided)."""
    return {
        1: "minimal movement, almost still, only tiny natural motion",
        2: "gentle subtle movement",
        3: "natural movement",
        4: "lively, clearly visible movement",
        5: "strong, energetic, dramatic movement",
    }.get(int(intensity), "natural movement")


def build_prompt(prompt: str, moves: list[str], cam_intensity: int, motion_prompt: str = "",
                 motion_intensity: int | None = None, character_desc: str = "") -> str:
    pieces = []
    if character_desc:
        pieces.append(character_desc.strip().rstrip("."))
    pieces.append(prompt.strip().rstrip("."))
    if motion_prompt:
        pieces.append(motion_prompt.strip().rstrip("."))
    if motion_intensity is not None:
        pieces.append(motion_text(motion_intensity))
    cam = camera_text(moves, cam_intensity)
    if cam:
        pieces.append(cam)
    return ". ".join(p for p in pieces if p) + "."
