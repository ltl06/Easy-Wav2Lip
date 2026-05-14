"""
Digital Human Pipeline
Orchestrates: Expression/View Generation -> Wav2Lip Lip Sync -> Video Composition
"""
import os
import cv2
import numpy as np
import subprocess
import tempfile
import shutil
import torch
import time
import threading
import cv2 as _cv2

from expression_control import ExpressionController
import analytics


def run_full_pipeline(job_id, source_path, audio_path, is_image, params, progress_callback=None):
    """
    Full digital human pipeline.
    1. Expression/View generation from source video/image
    2. Wav2Lip lip sync using audio
    3. Final video encoding

    Args:
        job_id: Unique job identifier
        source_path: Path to source video or image
        audio_path: Path to audio file
        is_image: Whether source is a single image
        params: Dict with all parameters
        progress_callback: Callback(pct, message) for progress updates
    Returns:
        Path to final output video
    """
    job_dir = os.path.join('temp', job_id)
    os.makedirs(job_dir, exist_ok=True)

    # ---- Analytics: determine source metadata ----
    frame_count = 0
    duration = 0.0
    if is_image:
        _img = _cv2.imread(source_path)
        frame_count = 1 if _img is not None else 0
    else:
        _cap = _cv2.VideoCapture(source_path)
        frame_count = int(_cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        _fps = _cap.get(_cv2.CAP_PROP_FPS)
        duration = frame_count / max(_fps, 1)
        _cap.release()

    analytics.record_job_start(
        job_id, params,
        source_type='image' if is_image else 'video',
        is_image=is_image,
        frame_count=frame_count,
        duration=duration,
    )

    _stop_sampling = threading.Event()

    def _sample_loop():
        while not _stop_sampling.wait(5):
            analytics.record_system_metrics(job_id)

    _metrics_thread = threading.Thread(target=_sample_loop, daemon=True)
    _metrics_thread.start()

    def _step(step_name, p, msg=''):
        analytics.record_step(job_id, step_name, p, msg)
        if progress_callback:
            progress_callback(p, msg)

    try:
        # ---- Step 1: Expression / View Generation ----
        _step('init', 5, '初始化表情控制器...')

        expr = ExpressionController(device='cuda' if torch.cuda.is_available() else 'cpu')
        has_advanced = (expr.fa is not None or expr.mp_face_mesh is not None)

        if has_advanced:
            _step('face_analysis', 10, '分析人脸特征...')
            if is_image:
                animated_img_path = os.path.join(job_dir, 'animated_source.jpg')
                expr.process_image(source_path, animated_img_path, params)
                source_frames = [_cv2.imread(animated_img_path)]
                view_output = os.path.join(job_dir, 'view_output.mp4')
                _frames_to_video(source_frames, view_output, fps=25, width=None, height=None)
                processed_video = view_output
            else:
                view_output = os.path.join(job_dir, 'view_output.mp4')
                expr.process_video(source_path, view_output, params,
                                 progress_callback=lambda p, m: _step('view_animation', 10 + int(p * 0.2), f'表情动画: {m}'))
                processed_video = view_output
            _step('expression_done', 25, '表情/视角生成完成')
        else:
            if is_image:
                source_frames = [_cv2.imread(source_path)]
                view_output = os.path.join(job_dir, 'view_output.mp4')
                _frames_to_video(source_frames, view_output, fps=25, width=None, height=None)
                processed_video = view_output
            else:
                processed_video = source_path
            _step('expression_skipped', 25, '跳过表情生成（未安装依赖）')

        # ---- Step 2: Wav2Lip Lip Sync ----
        _step('lip_sync_prepare', 30, '准备唇形同步...')

        import inference
        import audio as audio_module

        if audio_path and audio_path != processed_video:
            audio_for_lip = audio_path
        else:
            audio_for_lip = os.path.join(job_dir, 'audio.wav')
            subprocess.check_call([
                'ffmpeg', '-y', '-loglevel', 'error',
                '-i', processed_video,
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                audio_for_lip
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        from easy_functions import load_model
        quality = params.get('quality', 'Enhanced')
        checkpoint = 'checkpoints/Wav2Lip_GAN.pth' if quality == 'Experimental' else 'checkpoints/Wav2Lip.pth'

        if not os.path.exists(checkpoint):
            raise FileNotFoundError(f'Wav2Lip checkpoint not found: {checkpoint}. Run install.py first.')

        model = load_model(checkpoint)
        model.eval()
        inference.model = model
        inference.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        from batch_face import RetinaFace
        inference.detector = RetinaFace(gpu_id=0, model_path='checkpoints/mobilenet.pth', network='mobilenet')
        inference.detector_model = inference.detector.model

        args = _build_inference_args(processed_video, audio_for_lip, params, is_image)
        lip_output = os.path.join(job_dir, 'lip_output.mp4')
        args.outfile = lip_output

        _step('wav2lip', 35, '开始唇形同步处理...')

        inference.args = args
        inference.main()

        if not os.path.exists(lip_output):
            raise RuntimeError(f'Wav2Lip did not produce output: {lip_output}')

        _step('wav2lip_done', 85, '唇形同步完成')

        # ---- Step 3: Final Encoding ----
        _step('encode', 90, '编码最终视频...')

        output_path = os.path.join('results', f'{job_id}.mp4')
        os.makedirs('results', exist_ok=True)

        subprocess.check_call([
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', lip_output,
            '-i', audio_for_lip,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            output_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not os.path.exists(output_path):
            raise RuntimeError('Final video encoding failed')

        _step('complete', 100, '完成!')
        analytics.record_job_complete(job_id, status='completed')

    except Exception as _exc:
        analytics.record_job_complete(job_id, status='failed', error=str(_exc))
        raise

    finally:
        _stop_sampling.set()
        if _metrics_thread is not None:
            _metrics_thread.join(timeout=2)

    return output_path


def generate_preview(source_path, audio_path, is_image, params):
    """
    Generate a quick single-frame preview.
    Returns path to preview image.
    """
    job_dir = tempfile.mkdtemp(prefix='preview_')

    try:
        expr = ExpressionController(device='cuda' if torch.cuda.is_available() else 'cpu')

        preview_path = os.path.join(job_dir, 'preview.jpg')

        if is_image:
            expr.process_image(source_path, preview_path, params)
        else:
            cap = cv2.VideoCapture(source_path)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                raise ValueError('Could not read first frame from video')
            tmp_frame = os.path.join(job_dir, 'frame.jpg')
            cv2.imwrite(tmp_frame, frame)
            expr.process_image(tmp_frame, preview_path, params)

        dst = os.path.join('temp', 'preview.jpg')
        shutil.copy(preview_path, dst)
        return dst

    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _build_inference_args(video_path, audio_path, params, is_image=False):
    """Build argparse namespace from params dict."""
    import argparse

    args = argparse.Namespace(
        checkpoint_path='checkpoints/Wav2Lip.pth',
        face=video_path,
        audio=audio_path,
        outfile='temp/result.mp4',
        static=is_image,
        fps=25.0,
        pads=params.get('pads', [0, 10, 0, 0]),
        wav2lip_batch_size=1,
        out_height=int(params.get('output_height', 720)),
        crop=[0, -1, 0, -1],
        box=[-1, -1, -1, -1],
        rotate=False,
        nosmooth='False',
        no_seg=False,
        no_sr=False,
        sr_model='gfpgan',
        fullres=3,
        debug_mask='False',
        preview_settings='False',
        mouth_tracking='False',
        mask_dilation=2.5,
        mask_feathering=2,
        quality=params.get('quality', 'Enhanced'),
        img_size=96,
    )
    return args


def _frames_to_video(frames, output_path, fps=25, width=None, height=None):
    """Convert list of frames to video file."""
    if not frames:
        raise ValueError('No frames provided')

    h, w = frames[0].shape[:2]
    if width and height:
        w, h = width, height

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    for frame in frames:
        if width and height:
            frame = cv2.resize(frame, (w, h))
        out.write(frame)

    out.release()


if __name__ == '__main__':
    print('Digital Human Pipeline Test')
    print('=' * 40)

    # Check expression module
    from expression_control import check_dependencies
    check_dependencies()

    print('\nPipeline module loaded successfully.')
