from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
import os
import uuid
import shutil
import subprocess
import threading
import json
import time
from werkzeug.utils import secure_filename
import configparser

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
RESULTS_FOLDER = 'results'
ALLOWED_VIDEO = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
ALLOWED_IMAGE = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_AUDIO = {'mp3', 'wav', 'ogg', 'm4a', 'flac'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Job status tracking
jobs = {}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(TEMP_FOLDER, job_id)
        os.makedirs(job_dir, exist_ok=True)

        source_file = request.files.get('source')
        audio_file = request.files.get('audio')

        if not source_file:
            return jsonify({'error': 'No source file provided'}), 400

        source_name = secure_filename(source_file.filename)
        ext = source_name.rsplit('.', 1)[1].lower()

        is_image = ext in ALLOWED_IMAGE
        if is_image:
            source_path = os.path.join(job_dir, f'source.{ext}')
            source_file.save(source_path)
        else:
            if not allowed_file(source_name, ALLOWED_VIDEO):
                return jsonify({'error': 'Video format not allowed'}), 400
            source_path = os.path.join(job_dir, f'source.{ext}')
            source_file.save(source_path)

        audio_path = None
        if audio_file:
            audio_name = secure_filename(audio_file.filename)
            if not allowed_file(audio_name, ALLOWED_AUDIO):
                return jsonify({'error': 'Audio format not allowed'}), 400
            audio_path = os.path.join(job_dir, f'audio.{audio_name.rsplit(".", 1)[1]}')
            audio_file.save(audio_path)
        else:
            # Use audio from source video if available
            if not is_image:
                audio_path = source_path  # Will extract audio from video later

        jobs[job_id] = {
            'status': 'pending',
            'progress': 0,
            'source': source_path,
            'audio': audio_path,
            'is_image': is_image,
            'result': None,
            'error': None,
            'start_time': time.time(),
            'params': {}
        }

        return jsonify({'job_id': job_id, 'message': 'Files uploaded successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process', methods=['POST'])
def start_process():
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        if not job_id or job_id not in jobs:
            return jsonify({'error': 'Invalid job_id'}), 400

        job = jobs[job_id]
        job['params'] = {
            'view_params': data.get('view_params', {}),
            'quality': data.get('quality', 'Enhanced'),
            'output_height': data.get('output_height', 720),
            'head_rotation_x': data.get('head_rotation_x', 0.0),
            'head_rotation_y': data.get('head_rotation_y', 0.0),
            'head_rotation_z': data.get('head_rotation_z', 0.0),
            'blink_frequency': data.get('blink_frequency', 0.5),
            'expression_strength': data.get('expression_strength', 0.5),
            'pads': data.get('pads', [0, 10, 0, 0]),
        }

        thread = threading.Thread(target=run_pipeline, args=(job_id,))
        thread.daemon = True
        thread.start()

        return jsonify({'message': 'Processing started', 'job_id': job_id})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_pipeline(job_id):
    job = jobs[job_id]
    try:
        job['status'] = 'running'
        job['progress'] = 5
        update_progress(job_id, 'Starting pipeline...')

        # Import pipeline
        from pipeline import run_full_pipeline

        result_path = run_full_pipeline(
            job_id=job_id,
            source_path=job['source'],
            audio_path=job['audio'],
            is_image=job['is_image'],
            params=job['params'],
            progress_callback=lambda p, msg: update_progress(job_id, msg, p)
        )

        job['result'] = result_path
        job['status'] = 'completed'
        job['progress'] = 100
        update_progress(job_id, 'Done!', 100)

    except Exception as e:
        import traceback
        job['status'] = 'failed'
        job['error'] = str(e)
        job['traceback'] = traceback.format_exc()
        update_progress(job_id, f'Error: {str(e)}', -1)

def update_progress(job_id, message, progress=None):
    if job_id in jobs:
        jobs[job_id]['message'] = message
        if progress is not None:
            jobs[job_id]['progress'] = progress

@app.route('/api/status/<job_id>')
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'message': job.get('message', ''),
        'result': job.get('result'),
        'error': job.get('error')
    })

@app.route('/api/result/<job_id>')
def get_result(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    if job['status'] != 'completed' or not job['result']:
        return jsonify({'error': 'Result not ready'}), 400
    return send_file(job['result'], as_attachment=True, download_name='result.mp4')

@app.route('/api/preview/<job_id>')
def get_preview(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    preview_path = os.path.join(TEMP_FOLDER, job_id, 'preview.jpg')
    if os.path.exists(preview_path):
        return send_file(preview_path)
    return jsonify({'error': 'Preview not available'}), 404

@app.route('/api/quick_preview', methods=['POST'])
def quick_preview():
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        if not job_id or job_id not in jobs:
            return jsonify({'error': 'Invalid job_id'}), 400

        job = jobs[job_id]
        from pipeline import generate_preview

        preview_path = generate_preview(
            source_path=job['source'],
            audio_path=job['audio'],
            is_image=job['is_image'],
            params=job['params']
        )

        return jsonify({'preview_path': f'/api/preview/{job_id}'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return jsonify({
        'quality_options': ['Fast', 'Improved', 'Enhanced', 'Experimental'],
        'default_quality': config['OPTIONS'].get('quality', 'Enhanced'),
        'default_height': config['OPTIONS'].get('output_height', 'full resolution'),
    })


# ---- Analytics API ----

@app.route('/api/analytics/summary', methods=['GET'])
def analytics_summary():
    """Get aggregated analytics summary over last N days."""
    days = request.args.get('days', 7, type=int)
    try:
        import analytics as an
        summary = an.get_summary(days=days)
        # Compute overall totals
        total_jobs = sum(s['total_jobs'] for s in summary)
        completed = sum(s['completed_jobs'] for s in summary)
        failed = sum(s['failed_jobs'] for s in summary)
        total_frames = sum(s['total_frames'] for s in summary)
        total_duration = sum(s['total_duration_secs'] for s in summary)
        avg_cpu = sum(s['avg_cpu_percent'] * s['total_jobs'] for s in summary) / max(total_jobs, 1)
        avg_gpu = sum(s['avg_gpu_utilization'] * s['total_jobs'] for s in summary) / max(total_jobs, 1)
        return jsonify({
            'days': summary,
            'totals': {
                'total_jobs': total_jobs,
                'completed_jobs': completed,
                'failed_jobs': failed,
                'total_frames': total_frames,
                'total_duration_secs': round(total_duration, 1),
                'avg_cpu_percent': round(avg_cpu, 1),
                'avg_gpu_utilization': round(avg_gpu, 1),
                'success_rate': round(completed / max(total_jobs, 1) * 100, 1),
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/recent', methods=['GET'])
def analytics_recent():
    """Get recent jobs list."""
    limit = request.args.get('limit', 20, type=int)
    try:
        import analytics as an
        return jsonify({'jobs': an.get_recent_jobs(limit=limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/step_timing', methods=['GET'])
def analytics_step_timing():
    """Get average duration per pipeline step."""
    try:
        import analytics as an
        return jsonify({'steps': an.get_step_timing_stats()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/quality_breakdown', methods=['GET'])
def analytics_quality():
    """Get job count and avg duration by quality setting."""
    try:
        import analytics as an
        return jsonify({'quality': an.get_quality_breakdown()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/job/<job_id>', methods=['GET'])
def analytics_job_detail(job_id):
    """Get detailed metrics for a specific job."""
    try:
        import analytics as an
        return jsonify(an.get_job_detail(job_id))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
