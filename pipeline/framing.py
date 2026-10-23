"""Smart Speaker Framing & Dynamic Layout Engine.

Integrates lightweight, offline OpenCV face detection to:
1. Centering: Dynamically offset 9:16 vertical crop around active speaker face
   rather than static 50% dead center.
2. Split-Screen Layout: Stacks dual crops (Host / Speaker 1 on top, Guest / Speaker 2
   on bottom) with sleek accent dividers and ambient backdrop for 2-person podcast clips.
"""
from pathlib import Path
from statistics import median

# Safe OpenCV import with graceful fallback
try:
    import cv2
    _OPENCV_AVAILABLE = True
except Exception:
    cv2 = None
    _OPENCV_AVAILABLE = False


def _get_cascade():
    """Safely retrieves the Haar cascade classifier for face detection."""
    if not _OPENCV_AVAILABLE or cv2 is None:
        return None
    try:
        cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
        if Path(cascade_path).exists():
            return cv2.CascadeClassifier(cascade_path)
    except Exception as e:
        print(f"  [Framing] Warning: Could not initialize Haar cascade: {e}")
    return None


def detect_speaker_framing(
    video_path: Path | str,
    start_sec: float = 0.0,
    end_sec: float = 30.0,
    num_samples: int = 6,
) -> dict:
    """Analyzes a clip time window with OpenCV to find speaker face positions.

    Returns:
        dict:
            - has_faces: bool (True if at least one face detected)
            - has_two_speakers: bool (True if both left & right speaker clusters detected)
            - speaker1_x_ratio: float (0.18 to 0.82, horizontal center for upper panel / host)
            - speaker2_x_ratio: float (0.18 to 0.82, horizontal center for lower panel / guest)
            - dominant_x_ratio: float (0.18 to 0.82, dominant single speaker center)
            - frame_width: int
            - frame_height: int
    """
    default_result = {
        "has_faces": False,
        "has_two_speakers": False,
        "speaker1_x_ratio": 0.28,
        "speaker2_x_ratio": 0.72,
        "dominant_x_ratio": 0.50,
        "frame_width": 1920,
        "frame_height": 1080,
    }

    if not _OPENCV_AVAILABLE:
        return default_result

    v_path = Path(video_path)
    if not v_path.exists() or v_path.stat().st_size == 0:
        return default_result

    cascade = _get_cascade()
    if cascade is None:
        return default_result

    try:
        cap = cv2.VideoCapture(str(v_path))
        if not cap.isOpened():
            return default_result

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        clip_start_frame = max(0, int(start_sec * fps))
        clip_end_frame = min(total_frames, int(end_sec * fps)) if total_frames > 0 else int(end_sec * fps)
        frame_span = max(1, clip_end_frame - clip_start_frame)

        detected_xs = []

        # Sample evenly spaced frames across the clip window
        samples = min(num_samples, max(2, int(frame_span // 15)))
        for i in range(samples):
            target_frame = clip_start_frame + int((i + 0.5) * (frame_span / samples))
            if total_frames > 0 and target_frame >= total_frames:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Downsample to max width 640 for rapid face detection (< 15ms per frame)
            h, w = frame.shape[:2]
            scale = 1.0
            if w > 640:
                scale = 640.0 / w
                small = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
            else:
                small = frame

            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(32, 32),
            )

            for (fx, fy, fw, fh) in faces:
                # Map back to original coordinate space
                cx = (fx + fw / 2.0) / scale
                x_ratio = cx / float(w)
                detected_xs.append(x_ratio)

        cap.release()

        if not detected_xs:
            return {
                **default_result,
                "frame_width": width,
                "frame_height": height,
            }

        # Cluster face positions into left (< 0.45) and right (> 0.55) halves
        left_cluster = [x for x in detected_xs if x < 0.45]
        right_cluster = [x for x in detected_xs if x > 0.55]
        center_cluster = [x for x in detected_xs if 0.40 <= x <= 0.60]

        has_two_speakers = len(left_cluster) >= 1 and len(right_cluster) >= 1

        if has_two_speakers:
            s1 = median(left_cluster)
            s2 = median(right_cluster)
        elif len(left_cluster) > len(right_cluster):
            s1 = median(left_cluster)
            s2 = 0.72
        elif len(right_cluster) > len(left_cluster):
            s1 = 0.28
            s2 = median(right_cluster)
        else:
            s1 = 0.28
            s2 = 0.72

        dom = median(detected_xs)

        # Enforce safety bounds (keep framing inside 18% - 82% of widescreen)
        s1_clamped = max(0.18, min(0.48, float(s1)))
        s2_clamped = max(0.52, min(0.82, float(s2)))
        dom_clamped = max(0.18, min(0.82, float(dom)))

        return {
            "has_faces": True,
            "has_two_speakers": has_two_speakers,
            "speaker1_x_ratio": round(s1_clamped, 3),
            "speaker2_x_ratio": round(s2_clamped, 3),
            "dominant_x_ratio": round(dom_clamped, 3),
            "frame_width": width,
            "frame_height": height,
        }

    except Exception as e:
        print(f"  [Framing] Face detection notice: {e} (using default center framing)")
        return default_result
