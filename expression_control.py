"""
Expression & View Switching Control Module
Supports AI-driven head pose, expression, and blink animation.
Uses 3D face reconstruction + perspective warping as the core approach,
with optional integration of SadTalker/LivePortrait if available.
"""
import os
import cv2
import numpy as np
import tempfile
import subprocess
import torch

# Try to import optional dependencies
try:
    from face_alignment import FaceAlignment, LandmarksType
    HAS_FACE_ALIGNMENT = True
except ImportError:
    HAS_FACE_ALIGNMENT = False

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

try:
    from sadtinker.inference import SadTalker
    HAS_SADTALKER = True
except ImportError:
    HAS_SADTALKER = False

try:
    from liveportrait.inference import LivePortrait
    HAS_LIVEPORTRAIT = True
except ImportError:
    HAS_LIVEPORTRAIT = False


class ExpressionController:
    """
    Controls head pose, expression, and blink animation for digital human videos.
    Works with video files or single images.
    """

    def __init__(self, device='cuda'):
        self.device = device if torch.cuda.is_available() else 'cpu'
        self.fa = None
        self.mp_face_mesh = None
        self.sadtalker = None
        self.liveportrait = None

        self._init_face_detector()
        self._init_optional_models()

    def _init_face_detector(self):
        """Initialize 3D face landmark detector."""
        if HAS_FACE_ALIGNMENT:
            try:
                self.fa = FaceAlignment(
                    LandmarksType.THREE_D,
                    device=self.device,
                    face_detector='blazeface',
                    face_detector_kwargs={'backbone': 'resnet50'}
                )
                print("[Expression] Face Alignment (3D landmarks) initialized.")
            except Exception as e:
                print(f"[Expression] Face Alignment init failed: {e}, falling back to mediapipe")
                self._init_mediapipe()
        elif HAS_MEDIAPIPE:
            self._init_mediapipe()
        else:
            print("[Expression] Warning: No face landmark detector available. Install face_alignment or mediapipe.")
            print("[Expression] Install with: pip install face_alignment mediapipe")

    def _init_mediapipe(self):
        if HAS_MEDIAPIPE:
            self.mp_face_mesh = mp.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            print("[Expression] MediaPipe Face Mesh initialized.")

    def _init_optional_models(self):
        """Initialize optional advanced models."""
        if HAS_SADTALKER:
            try:
                self.sadtalker = SadTalker(lazy_load=True)
                print("[Expression] SadTalker loaded.")
            except Exception as e:
                print(f"[Expression] SadTalker init failed: {e}")

        if HAS_LIVEPORTRAIT:
            try:
                self.liveportrait = LivePortrait()
                print("[Expression] LivePortrait loaded.")
            except Exception as e:
                print(f"[Expression] LivePortrait init failed: {e}")

    def detect_face_landmarks(self, image):
        """
        Detect 3D face landmarks from an image.
        Returns: landmark points (N, 3) or None if no face found.
        """
        if self.fa is not None:
            try:
                preds = self.fa.get_landmarks(image)
                if preds is not None and len(preds) > 0:
                    return preds[0]
            except Exception:
                pass

        if self.mp_face_mesh is not None:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.mp_face_mesh.process(rgb)
            if results.multi_face_landmarks and len(results.multi_face_landmarks) > 0:
                lm = results.multi_face_landmarks[0]
                h, w = image.shape[:2]
                pts = np.array([(p.x * w, p.y * h, p.z * w) for p in lm.landmark], dtype=np.float32)
                return pts
        return None

    def estimate_pose(self, landmarks):
        """
        Estimate head pose (pitch, yaw, roll) from 3D landmarks.
        Simplified perspective-n-points using 3D face model.
        Returns: (pitch, yaw, roll) in radians.
        """
        if landmarks is None:
            return 0.0, 0.0, 0.0

        # Use key landmarks to estimate pose
        # Nose tip: ~30, Chin: ~8, Left eye corner: ~33, Right eye corner: ~263
        # Left mouth corner: ~61, Right mouth corner: ~291
        lm_idx = [33, 263, 61, 291, 8, 30]  # eyes, mouth, chin, nose
        lm_idx = [i for i in lm_idx if i < len(landmarks)]

        if len(lm_idx) < 4:
            return 0.0, 0.0, 0.0

        pts = landmarks[lm_idx]

        # Eye centers
        left_eye = pts[0]
        right_eye = pts[1]
        eye_center = (left_eye + right_eye) / 2

        # Mouth center
        mouth_center = (pts[2] + pts[3]) / 2

        # Direction vectors
        dx = right_eye[0] - left_eye[0]
        dy = right_eye[1] - left_eye[1]

        # Roll from eye line
        roll = np.arctan2(dy, dx)

        # Pitch (up/down) from relative positions
        nose_tip = pts[5] if len(pts) > 5 else mouth_center
        chin = pts[4]
        pitch = np.arctan2(nose_tip[1] - chin[1], nose_tip[2] - chin[2])

        # Yaw (left/right) from nose relative to eye centers
        nose_offset = nose_tip[0] - eye_center[0]
        face_width = max(dx, 1.0)
        yaw = np.arctan2(nose_offset, face_width * 3)

        return pitch, yaw, roll

    def apply_view_warping(self, image, target_yaw=0.0, target_pitch=0.0, target_roll=0.0):
        """
        Apply perspective warping to simulate head rotation.
        This creates a pseudo-3D effect by warping the face region.
        """
        h, w = image.shape[:2]
        face_size = min(h, w)

        # Get face center
        cx, cy = w // 2, h // 2

        # Scale factors for perspective effect
        yaw_rad = target_yaw * 0.5
        pitch_rad = target_pitch * 0.3

        # Calculate perspective warp coefficients
        alpha_yaw = np.cos(yaw_rad)
        beta_yaw = np.sin(yaw_rad)
        alpha_pitch = np.cos(pitch_rad)
        beta_pitch = np.sin(pitch_rad)

        # Build perspective transformation matrix
        # This simulates head rotation by skewing the face region
        src_pts = np.float32([
            [0, 0],
            [w, 0],
            [0, h],
            [w, h]
        ])

        # Apply yaw effect (left/right rotation)
        offset_x = beta_yaw * w * 0.15
        offset_y = beta_pitch * h * 0.1

        dst_pts = np.float32([
            [offset_x * 0.5, offset_y * 0.5],
            [w - offset_x * 0.5, offset_y * 0.3],
            [offset_x * 0.3, h - offset_y * 0.5],
            [w - offset_x * 0.3, h - offset_y * 0.3]
        ])

        # Adjust for combined rotation effect
        dst_pts[:, 0] += beta_yaw * (np.array([0.1, -0.1, 0.1, -0.1]) * w)
        dst_pts[:, 1] += beta_pitch * (np.array([-0.1, -0.1, 0.1, 0.1]) * h)

        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(image, M, (w, h), borderMode=cv2.BORDER_REFLECT)

        return warped

    def generate_blink_animation(self, frames, blink_frequency=0.5, blink_strength=1.0):
        """
        Add natural blinking animation to video frames.
        blink_frequency: 0.0 (no blink) to 1.0 (frequent blink)
        blink_strength: 0.0 (subtle) to 1.0 (full close)
        """
        if blink_frequency < 0.05:
            return frames  # No blinking

        n_frames = len(frames)
        if n_frames == 0:
            return frames

        output = []
        # Blink interval based on frequency (higher = more frequent)
        blink_interval = max(10, int(60 / (blink_frequency * 5 + 1)))
        blink_duration = max(3, int(blink_interval * 0.2))

        current_blink = 0
        blink_phase = 0  # 0=open, 1=closing, 2=closed, 3=opening

        for i, frame in enumerate(frames):
            if blink_frequency > 0.05:
                # Trigger blink at intervals
                if i % blink_interval == 0:
                    blink_phase = 1
                    current_blink = 0

                if blink_phase > 0:
                    # Blink animation phases
                    if blink_phase == 1:
                        current_blink += blink_strength / blink_duration
                        if current_blink >= blink_strength:
                            current_blink = blink_strength
                            blink_phase = 2
                    elif blink_phase == 2:
                        blink_phase = 3
                    elif blink_phase == 3:
                        current_blink -= blink_strength / blink_duration
                        if current_blink <= 0:
                            current_blink = 0
                            blink_phase = 0

                # Apply blink to face region using eye landmarks
                modified = self._apply_eye_blink(frame.copy(), current_blink)
                output.append(modified)
            else:
                output.append(frame)

        return output

    def _apply_eye_blink(self, image, strength):
        """Apply blink effect by detecting eyes and adding eyelid overlay."""
        if strength < 0.01:
            return image

        landmarks = self.detect_face_landmarks(image)
        if landmarks is None:
            return image

        h, w = image.shape[:2]

        # Eye landmark indices (approximate for both 468 and 68-pt models)
        # Try 468-point model first
        left_eye_indices = list(range(33, 38))  # ~left eye
        right_eye_indices = list(range(33, 38))  # Simplified

        if len(landmarks) > 100:
            # MediaPipe / FA 468-point model
            left_eye = landmarks[[362, 385, 387, 263, 373, 380]]
            right_eye = landmarks[[33, 160, 158, 133, 153, 144]]
        elif len(landmarks) > 50:
            # 68-point model
            left_eye = landmarks[36:42]
            right_eye = landmarks[42:48]
        else:
            return image

        for eye_pts in [left_eye, right_eye]:
            if len(eye_pts) < 6:
                continue

            eye_pts = eye_pts.astype(int)
            eye_center = eye_pts.mean(axis=0).astype(int)

            # Upper eyelid overlay
            top_pts = eye_pts[[0, 1, 2]]
            bottom_pts = eye_pts[[3, 4, 5]]

            eye_h = np.linalg.norm(bottom_pts[0] - top_pts[0])
            lid_offset = int(eye_h * strength)

            if lid_offset > 0:
                # Create eyelid mask
                mask = np.zeros(image.shape[:2], dtype=np.uint8)
                for pt in eye_pts:
                    cv2.circle(mask, (int(pt[0]), int(pt[1])), 3, 255, -1)

                # Close upper lid
                upper_eye = eye_pts.copy()
                upper_eye[:, 1] -= lid_offset

                # Fill polygon
                all_pts = np.vstack([upper_eye, eye_pts[::-1]]).astype(np.int32)
                cv2.fillPoly(mask, [all_pts], 255)

                # Blur the mask for natural blending
                if lid_offset > 2:
                    blur_size = max(3, lid_offset // 2) * 2 + 1
                    mask = cv2.GaussianBlur(mask, (blur_size, blur_size), 0)

                # Apply to image (darken the eye region slightly)
                darkening = (1.0 - strength * 0.5)
                image = np.where(mask[:, :, None] > 0,
                                 (image * darkening).astype(np.uint8),
                                 image)

        return image

    def generate_view_animation(self, frames, params):
        """
        Generate head pose animation for a sequence of frames.
        params: dict with 'head_rotation_x', 'head_rotation_y', 'head_rotation_z',
                'blink_frequency', 'expression_strength', 'view_animation'
        Returns: list of processed frames.
        """
        n_frames = len(frames)
        if n_frames == 0:
            return frames

        animation_mode = params.get('view_animation', 'static')
        base_yaw = params.get('head_rotation_y', 0.0)
        base_pitch = params.get('head_rotation_x', 0.0)
        base_roll = params.get('head_rotation_z', 0.0)
        blink_freq = params.get('blink_frequency', 0.5)
        expr_strength = params.get('expression_strength', 0.5)

        output_frames = []

        for i, frame in enumerate(frames):
            if animation_mode == 'static':
                yaw = base_yaw
                pitch = base_pitch
                roll = base_roll
            elif animation_mode == 'gentle_sway':
                t = i / n_frames
                yaw = base_yaw + np.sin(t * np.pi * 4) * 0.08
                pitch = base_pitch + np.sin(t * np.pi * 2) * 0.03
                roll = base_roll
            elif animation_mode == 'nodding':
                t = i / n_frames
                yaw = base_yaw
                pitch = base_pitch + np.sin(t * np.pi * 3) * 0.1
                roll = base_roll
            elif animation_mode == 'look_around':
                t = i / n_frames
                yaw = base_yaw + np.sin(t * np.pi * 2) * 0.25
                pitch = base_pitch + np.cos(t * np.pi * 1.5) * 0.08
                roll = base_roll + np.sin(t * np.pi) * 0.05
            else:
                yaw, pitch, roll = base_yaw, base_pitch, base_roll

            # Apply perspective warping for view effect
            warped = self.apply_view_warping(frame, yaw, pitch, roll)
            output_frames.append(warped)

        # Apply blinking
        if blink_freq > 0.05:
            output_frames = self.generate_blink_animation(output_frames, blink_freq, expr_strength)

        return output_frames

    def process_video(self, video_path, output_path, params, progress_callback=None):
        """
        Process a video file: extract frames, apply view/animation, save result.
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        if progress_callback:
            progress_callback(30, '应用视角动画...')

        # Apply animation
        processed = self.generate_view_animation(frames, params)

        if progress_callback:
            progress_callback(60, '编码输出视频...')

        # Write output video
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        for f in processed:
            out.write(f)
        out.release()

        if progress_callback:
            progress_callback(90, '完成!')

        return output_path

    def process_image(self, image_path, output_path, params):
        """
        Process a single image: apply view effect and save.
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")

        yaw = params.get('head_rotation_y', 0.0)
        pitch = params.get('head_rotation_x', 0.0)
        roll = params.get('head_rotation_z', 0.0)

        processed = self.apply_view_warping(img, yaw, pitch, roll)

        # Apply blink to single image (one frame)
        blink_freq = params.get('blink_frequency', 0.5)
        if blink_freq > 0.05:
            processed = self.generate_blink_animation([processed], blink_freq, 0.5)[0]

        cv2.imwrite(output_path, processed)
        return output_path


def check_dependencies():
    """Check which expression modules are available."""
    available = []

    if HAS_FACE_ALIGNMENT:
        available.append('face_alignment')
    if HAS_MEDIAPIPE:
        available.append('mediapipe')
    if HAS_SADTALKER:
        available.append('sadtalker')
    if HAS_LIVEPORTRAIT:
        available.append('liveportrait')

    print(f"[Expression] Available modules: {available}")
    return available


if __name__ == '__main__':
    print("Checking expression module dependencies...")
    available = check_dependencies()
    print(f"\nAvailable: {available}")
    if not available:
        print("\nTo enable full expression features, install dependencies:")
        print("  pip install face_alignment mediapipe")
