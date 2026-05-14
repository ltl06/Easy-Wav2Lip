"""
Analytics Module for Digital Human Pipeline
Collects, stores, and aggregates performance metrics and job statistics.
"""
import os
import json
import time
import sqlite3
import threading
import psutil
from datetime import datetime, timedelta
from collections import defaultdict

ANALYTICS_DIR = 'analytics'
os.makedirs(ANALYTICS_DIR, exist_ok=True)

DB_PATH = os.path.join(ANALYTICS_DIR, 'jobs.db')


def _get_db():
    """Get a thread-local database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_db()
    try:
        cursor = conn.cursor()

        # Jobs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                source_type TEXT,
                quality TEXT,
                output_height INTEGER,
                is_image INTEGER,
                frame_count INTEGER,
                duration REAL,
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                error TEXT,
                view_animation TEXT,
                head_rotation_x REAL,
                head_rotation_y REAL,
                head_rotation_z REAL,
                expression_strength REAL,
                blink_frequency REAL
            )
        ''')

        # Steps table (detailed timing for each pipeline step)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                step_name TEXT,
                started_at REAL,
                ended_at REAL,
                duration_ms REAL,
                progress_pct INTEGER,
                message TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            )
        ''')

        # System metrics table (GPU/CPU/RAM sampled during execution)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                sampled_at REAL,
                cpu_percent REAL,
                memory_used_gb REAL,
                memory_percent REAL,
                gpu_memory_used_gb REAL,
                gpu_memory_total_gb REAL,
                gpu_utilization REAL,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            )
        ''')

        # Daily stats (pre-aggregated for fast dashboard queries)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_jobs INTEGER,
                completed_jobs INTEGER,
                failed_jobs INTEGER,
                total_duration_secs REAL,
                total_frames INTEGER,
                avg_duration_secs REAL,
                avg_cpu_percent REAL,
                avg_gpu_utilization REAL,
                updated_at TEXT
            )
        ''')

        conn.commit()
    finally:
        conn.close()


def record_job_start(job_id, params, source_type='video', is_image=False,
                     frame_count=0, duration=0.0):
    """Record when a job starts."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO jobs
            (job_id, status, source_type, quality, output_height, is_image,
             frame_count, duration, created_at, started_at, view_animation,
             head_rotation_x, head_rotation_y, head_rotation_z,
             expression_strength, blink_frequency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_id, 'running', source_type,
            params.get('quality', 'Enhanced'),
            int(params.get('output_height', 720)),
            1 if is_image else 0,
            frame_count, duration,
            datetime.now().isoformat(),
            datetime.now().isoformat(),  # started_at
            params.get('view_animation', 'static'),
            float(params.get('head_rotation_x', 0.0)),
            float(params.get('head_rotation_y', 0.0)),
            float(params.get('head_rotation_z', 0.0)),
            float(params.get('expression_strength', 0.5)),
            float(params.get('blink_frequency', 0.5)),
        ))
        conn.commit()
    finally:
        conn.close()


def record_job_complete(job_id, status='completed', error=None):
    """Record when a job completes."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE jobs
            SET status = ?, completed_at = ?, error = ?
            WHERE job_id = ?
        ''', (status, datetime.now().isoformat(), error, job_id))
        conn.commit()

        # Update daily stats
        _update_daily_stats()
    finally:
        conn.close()


def record_step(job_id, step_name, progress_pct, message=''):
    """Record a pipeline step with timing."""
    ts = time.time()
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO job_steps (job_id, step_name, started_at, progress_pct, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (job_id, step_name, ts, progress_pct, message))
        conn.commit()
    finally:
        conn.close()


def record_system_metrics(job_id):
    """Sample current system resource usage."""
    ts = time.time()
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    mem_used_gb = mem.used / (1024 ** 3)

    gpu_data = {
        'gpu_memory_used_gb': 0.0,
        'gpu_memory_total_gb': 0.0,
        'gpu_utilization': 0.0,
    }

    try:
        import torch
        if torch.cuda.is_available():
            gpu_data['gpu_memory_used_gb'] = torch.cuda.memory_allocated() / (1024 ** 3)
            gpu_data['gpu_memory_total_gb'] = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            try:
                # Try to get GPU utilization on Windows
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    gpu_data['gpu_utilization'] = float(result.stdout.strip().split('\n')[0])
            except Exception:
                pass
    except Exception:
        pass

    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO system_metrics
            (job_id, sampled_at, cpu_percent, memory_used_gb, memory_percent,
             gpu_memory_used_gb, gpu_memory_total_gb, gpu_utilization)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_id, ts, cpu, mem_used_gb, mem.percent,
            gpu_data['gpu_memory_used_gb'],
            gpu_data['gpu_memory_total_gb'],
            gpu_data['gpu_utilization'],
        ))
        conn.commit()
    finally:
        conn.close()


def _update_daily_stats():
    """Recompute daily aggregation from jobs table."""
    today = datetime.now().date().isoformat()
    conn = _get_db()
    try:
        cursor = conn.cursor()

        # Aggregate from completed jobs
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status IN ('completed','failed') THEN
                    (julianday(completed_at) - julianday(started_at)) * 86400.0
                    ELSE 0 END) as total_duration,
                SUM(frame_count) as total_frames,
                AVG(CASE WHEN status IN ('completed','failed') THEN
                    (julianday(completed_at) - julianday(started_at)) * 86400.0
                    ELSE NULL END) as avg_duration
            FROM jobs
            WHERE date(created_at) = ?
        ''', (today,))
        row = cursor.fetchone()

        # Get avg system metrics from today's jobs
        cursor.execute('''
            SELECT
                AVG(s.cpu_percent) as avg_cpu,
                AVG(s.gpu_utilization) as avg_gpu
            FROM system_metrics s
            JOIN jobs j ON s.job_id = j.job_id
            WHERE date(j.created_at) = ?
        ''', (today,))
        metrics_row = cursor.fetchone()

        cursor.execute('''
            INSERT OR REPLACE INTO daily_stats
            (date, total_jobs, completed_jobs, failed_jobs, total_duration_secs,
             total_frames, avg_duration_secs, avg_cpu_percent, avg_gpu_utilization, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            today,
            row['total'] or 0,
            row['completed'] or 0,
            row['failed'] or 0,
            row['total_duration'] or 0.0,
            row['total_frames'] or 0,
            row['avg_duration'] or 0.0,
            metrics_row['avg_cpu'] or 0.0,
            metrics_row['avg_gpu'] or 0.0,
            datetime.now().isoformat(),
        ))
        conn.commit()
    finally:
        conn.close()


def get_summary(days=7):
    """Get aggregated stats over the last N days."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM daily_stats
            WHERE date >= date('now', ?)
            ORDER BY date DESC
        ''', (f'-{days} days',))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job_detail(job_id):
    """Get detailed info for a specific job."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
        job = cursor.fetchone()

        cursor.execute('SELECT * FROM job_steps WHERE job_id = ? ORDER BY started_at', (job_id,))
        steps = cursor.fetchall()

        cursor.execute('''
            SELECT MIN(sampled_at) as start, MAX(sampled_at) as end,
                   AVG(cpu_percent) as avg_cpu, MAX(cpu_percent) as max_cpu,
                   AVG(gpu_utilization) as avg_gpu, MAX(gpu_utilization) as max_gpu,
                   AVG(memory_used_gb) as avg_mem_gb, MAX(memory_used_gb) as max_mem_gb
            FROM system_metrics WHERE job_id = ?
        ''', (job_id,))
        metrics = cursor.fetchone()

        return {
            'job': dict(job) if job else None,
            'steps': [dict(s) for s in steps],
            'metrics': dict(metrics) if metrics and metrics['start'] else None,
        }
    finally:
        conn.close()


def get_recent_jobs(limit=20):
    """Get recent jobs list."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT job_id, status, source_type, quality, output_height,
                   frame_count, duration, created_at, completed_at, error
            FROM jobs ORDER BY created_at DESC LIMIT ?
        ''', (limit,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_step_timing_stats():
    """Get average duration per pipeline step (across all jobs)."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT step_name,
                   COUNT(*) as count,
                   AVG(duration_ms) as avg_ms,
                   MIN(duration_ms) as min_ms,
                   MAX(duration_ms) as max_ms
            FROM job_steps
            WHERE duration_ms IS NOT NULL
            GROUP BY step_name
            ORDER BY avg_ms DESC
        ''')
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_quality_breakdown():
    """Get job count grouped by quality setting."""
    conn = _get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT quality, COUNT(*) as count,
                   AVG(CASE WHEN status='completed' THEN
                       (julianday(completed_at) - julianday(started_at)) * 86400.0
                       ELSE NULL END) as avg_duration
            FROM jobs
            GROUP BY quality
            ORDER BY count DESC
        ''')
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


# Initialize DB on module import
init_db()
