let currentJobId = null;
let sourceFile = null;
let audioFile = null;
let currentResultPath = null;

// DOM elements
const uploadArea = document.getElementById('uploadArea');
const sourceInput = document.getElementById('sourceInput');
const audioUploadArea = document.getElementById('audioUploadArea');
const audioInput = document.getElementById('audioInput');
const processBtn = document.getElementById('processBtn');
const quickPreviewBtn = document.getElementById('quickPreviewBtn');
const progressSection = document.getElementById('progressSection');
const resultSection = document.getElementById('resultSection');

// ---- Drag & Drop ----
function setupDragDrop(el, input, isImage) {
    el.addEventListener('click', () => input.click());

    el.addEventListener('dragover', (e) => {
        e.preventDefault();
        el.classList.add('drag-over');
    });

    el.addEventListener('dragleave', () => {
        el.classList.remove('drag-over');
    });

    el.addEventListener('drop', (e) => {
        e.preventDefault();
        el.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file, input, isImage);
    });
}

setupDragDrop(uploadArea, sourceInput, true);
setupDragDrop(audioUploadArea, audioInput, false);

sourceInput.addEventListener('change', () => {
    if (sourceInput.files[0]) handleFileSelect(sourceInput.files[0], sourceInput, true);
});
audioInput.addEventListener('change', () => {
    if (audioInput.files[0]) handleFileSelect(audioInput.files[0], audioInput, false);
});

// ---- File Handling ----
async function handleFileSelect(file, input, isMedia) {
    const isImage = /\.(jpg|jpeg|png|webp)$/i.test(file.name);
    const isVideo = /\.(mp4|avi|mov|mkv|webm)$/i.test(file.name);
    const isAudio = /\.(mp3|wav|ogg|m4a|flac)$/i.test(file.name);

    if (isMedia) {
        if (!isImage && !isVideo) {
            showToast('请上传图片或视频文件', 'error');
            return;
        }
        sourceFile = file;
        showSourceInfo(file, isImage ? '图片' : '视频');
        showSourcePreview(file, isImage);
        updateButtons();
    } else {
        if (!isAudio) {
            showToast('请上传音频文件', 'error');
            return;
        }
        audioFile = file;
        showAudioInfo(file);
        updateButtons();
    }
}

function showSourceInfo(file, type) {
    const info = document.getElementById('sourceInfo');
    document.getElementById('sourceName').textContent = file.name;
    document.getElementById('sourceType').textContent = type;
    info.style.display = 'flex';
}

function showSourcePreview(file, isImage) {
    const preview = document.getElementById('sourcePreview');
    preview.style.display = 'block';
    if (isImage) {
        preview.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="preview">`;
    } else {
        preview.innerHTML = `<video src="${URL.createObjectURL(file)}" controls muted></video>`;
    }
}

function showAudioInfo(file) {
    const info = document.getElementById('audioInfo');
    document.getElementById('audioName').textContent = file.name;
    document.getElementById('audioType').textContent = '音频';
    info.style.display = 'flex';
}

function clearSource() {
    sourceFile = null;
    document.getElementById('sourceInfo').style.display = 'none';
    document.getElementById('sourcePreview').style.display = 'none';
    sourceInput.value = '';
    updateButtons();
}

function clearAudio() {
    audioFile = null;
    document.getElementById('audioInfo').style.display = 'none';
    audioInput.value = '';
    updateButtons();
}

function updateButtons() {
    processBtn.disabled = !sourceFile;
    quickPreviewBtn.disabled = !sourceFile;
}

// ---- Parameter Sliders ----
document.querySelectorAll('input[type="range"]').forEach(slider => {
    slider.addEventListener('input', () => {
        const valEl = document.getElementById(slider.id + 'Val');
        if (valEl) valEl.textContent = parseFloat(slider.value).toFixed(2);
    });
});

// ---- Upload & Process ----
async function uploadFiles() {
    const formData = new FormData();
    formData.append('source', sourceFile);
    if (audioFile) formData.append('audio', audioFile);

    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    return data.job_id;
}

function getViewParams() {
    return {
        head_rotation_x: parseFloat(document.getElementById('headRotationX').value),
        head_rotation_y: parseFloat(document.getElementById('headRotationY').value),
        head_rotation_z: parseFloat(document.getElementById('headRotationZ').value),
        expression_strength: parseFloat(document.getElementById('expressionStrength').value),
        blink_frequency: parseFloat(document.getElementById('blinkFrequency').value),
        view_animation: document.getElementById('viewAnimation').value,
    };
}

async function startProcess() {
    if (!sourceFile) return;

    setProcessing(true);
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    resetSteps();

    try {
        currentJobId = await uploadFiles();

        const params = getViewParams();
        params.quality = document.querySelector('input[name="quality"]:checked').value;
        params.output_height = parseInt(document.getElementById('outputHeight').value);

        const res = await fetch('/api/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: currentJobId, ...params })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        pollStatus();

    } catch (e) {
        showToast('处理失败: ' + e.message, 'error');
        setProcessing(false);
    }
}

async function quickPreview() {
    if (!sourceFile) return;

    setProcessing(true);
    progressSection.style.display = 'block';
    resetSteps();

    try {
        currentJobId = await uploadFiles();
        const params = getViewParams();
        params.quality = document.querySelector('input[name="quality"]:checked').value;
        params.output_height = parseInt(document.getElementById('outputHeight').value);

        await fetch('/api/quick_preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: currentJobId, ...params })
        });

        // For now, just show a message that preview is processing
        updateProgress(50, '生成预览中...');
        showToast('预览生成中，请稍候...', 'success');

    } catch (e) {
        showToast('预览失败: ' + e.message, 'error');
        setProcessing(false);
    }
}

async function pollStatus() {
    if (!currentJobId) return;

    try {
        const res = await fetch(`/api/status/${currentJobId}`);
        const data = await res.json();

        if (data.status === 'running' || data.status === 'pending') {
            updateProgress(data.progress, data.message);
            setTimeout(pollStatus, 1000);
        } else if (data.status === 'completed') {
            updateProgress(100, '处理完成!');
            setTimeout(() => {
                showResult();
                setProcessing(false);
            }, 500);
        } else if (data.status === 'failed') {
            showToast('处理失败: ' + (data.error || '未知错误'), 'error');
            setProcessing(false);
        }

    } catch (e) {
        console.error('Poll error:', e);
        setTimeout(pollStatus, 2000);
    }
}

function updateProgress(percent, message) {
    document.getElementById('progressBar').style.width = percent + '%';
    document.getElementById('progressPercent').textContent = percent + '%';
    document.getElementById('progressText').textContent = message;

    // Update steps
    const steps = ['step-upload', 'step-face', 'step-expression', 'step-lip', 'step-encode'];
    const thresholds = [5, 25, 50, 75, 95];

    steps.forEach((id, i) => {
        const el = document.getElementById(id);
        el.classList.remove('active', 'done');
        if (percent >= 100) {
            el.classList.add('done');
        } else if (percent >= thresholds[i] && i === steps.length - 1) {
            el.classList.add('active');
        } else if (percent >= thresholds[i]) {
            el.classList.add('done');
        } else if (i > 0 && percent >= thresholds[i - 1] && percent < thresholds[i]) {
            el.classList.add('active');
        }
    });
}

function resetSteps() {
    document.querySelectorAll('.step').forEach(el => {
        el.classList.remove('active', 'done');
    });
}

function showResult() {
    resultSection.style.display = 'block';
    const preview = document.getElementById('resultPreview');
    preview.innerHTML = `<video src="/api/result/${currentJobId}" controls autoplay></video>`;
    currentResultPath = `/api/result/${currentJobId}`;
    showToast('视频生成完成!', 'success');
}

function downloadResult() {
    if (currentResultPath) {
        window.open(currentResultPath, '_blank');
    }
}

function resetProcess() {
    currentJobId = null;
    currentResultPath = null;
    sourceFile = null;
    audioFile = null;
    clearSource();
    clearAudio();
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    setProcessing(false);
    updateButtons();
}

function setProcessing(processing) {
    processBtn.disabled = processing;
    quickPreviewBtn.disabled = processing || !sourceFile;
}

// ---- Toast ----
function showToast(message, type = 'info') {
    let toast = document.querySelector('.toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = 'toast show ' + type;
    setTimeout(() => { toast.classList.remove('show'); }, 4000);
}

// ---- Analytics Dashboard ----
async function loadAnalytics() {
    const days = document.getElementById('analyticsDays')?.value || '7';
    try {
        // Load summary
        const res = await fetch(`/api/analytics/summary?days=${days}`);
        const data = await res.json();

        if (data.error) {
            console.error('Analytics error:', data.error);
            return;
        }

        const t = data.totals;
        document.getElementById('statTotalJobs').textContent = t.total_jobs || 0;
        document.getElementById('statCompleted').textContent = t.completed_jobs || 0;
        document.getElementById('statFailed').textContent = t.failed_jobs || 0;
        document.getElementById('statFrames').textContent = (t.total_frames || 0).toLocaleString();
        document.getElementById('statDuration').textContent = _formatDuration(t.total_duration_secs);
        document.getElementById('statSuccessRate').textContent = t.success_rate + '%';
        document.getElementById('statCpu').textContent = t.avg_cpu_percent + '%';
        document.getElementById('statGpu').textContent = t.avg_gpu_utilization + '%';

        // Daily chart
        renderDailyChart(data.days);

        // Load step timings
        await loadStepTimings();

        // Load quality breakdown
        await loadQualityBreakdown();

        // Load recent jobs
        await loadRecentJobs();

    } catch (e) {
        console.error('Failed to load analytics:', e);
    }
}

async function loadStepTimings() {
    try {
        const res = await fetch('/api/analytics/step_timing');
        const data = await res.json();
        const container = document.getElementById('stepTimings');
        if (!data.steps || data.steps.length === 0) {
            container.innerHTML = '<div class="analytics-empty">暂无数据</div>';
            return;
        }
        const maxMs = Math.max(...data.steps.map(s => s.avg_ms));
        container.innerHTML = data.steps.map(s => `
            <div class="step-timing-row">
                <div class="step-timing-label">${_stepLabel(s.step_name)}</div>
                <div class="step-timing-bar-wrapper">
                    <div class="step-timing-bar" style="width:${(s.avg_ms / maxMs * 100).toFixed(1)}%"></div>
                </div>
                <div class="step-timing-value">${_formatDuration(s.avg_ms / 1000)}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to load step timings:', e);
    }
}

async function loadQualityBreakdown() {
    try {
        const res = await fetch('/api/analytics/quality_breakdown');
        const data = await res.json();
        const container = document.getElementById('qualityBreakdown');
        if (!data.quality || data.quality.length === 0) {
            container.innerHTML = '<div class="analytics-empty">暂无数据</div>';
            return;
        }
        container.innerHTML = `<div class="quality-grid">` + data.quality.map(q => `
            <div class="quality-tag">
                <span class="quality-tag-count">${q.count}</span>
                <span class="quality-tag-label">${q.quality}</span>
                ${q.avg_duration ? `<span class="quality-tag-duration">~${_formatDuration(q.avg_duration)}</span>` : ''}
            </div>
        `).join('') + `</div>`;
    } catch (e) {
        console.error('Failed to load quality breakdown:', e);
    }
}

async function loadRecentJobs() {
    try {
        const res = await fetch('/api/analytics/recent?limit=15');
        const data = await res.json();
        const container = document.getElementById('recentJobs');
        if (!data.jobs || data.jobs.length === 0) {
            container.innerHTML = '<div class="analytics-empty">暂无任务记录</div>';
            return;
        }
        container.innerHTML = `<div class="job-list">` + data.jobs.map(j => `
            <div class="job-item">
                <div class="job-status ${j.status}"></div>
                <div class="job-info">
                    <div class="job-name">${j.source_type} · ${j.quality} · ${j.output_height}p</div>
                    <div class="job-meta">${j.frame_count > 0 ? j.frame_count + ' 帧' : ''} ${j.duration > 0 ? '· ' + j.duration.toFixed(1) + 's' : ''}</div>
                </div>
                <div class="job-time">${_formatDate(j.created_at)}</div>
            </div>
        `).join('') + `</div>`;
    } catch (e) {
        console.error('Failed to load recent jobs:', e);
    }
}

function renderDailyChart(daysData) {
    const container = document.getElementById('dailyChart');
    if (!daysData || daysData.length === 0) {
        container.innerHTML = '<div class="analytics-empty">暂无数据</div>';
        return;
    }
    const maxJobs = Math.max(...daysData.map(d => d.total_jobs), 1);
    const bars = [];
    for (let i = daysData.length - 1; i >= 0; i--) {
        const dayData = daysData[i];
        const dateStr = dayData.date;
        const label = dateStr.slice(5); // MM-DD
        const h = Math.max(dayData.total_jobs / maxJobs * 70, dayData.total_jobs > 0 ? 4 : 2);
        const hasFail = dayData.failed_jobs > 0;
        bars.push(`
            <div class="chart-bar-wrapper" title="${dateStr}: ${dayData.total_jobs} 任务 (${dayData.completed_jobs} 成功, ${dayData.failed_jobs} 失败)">
                <div class="chart-bar${hasFail ? ' failed' : ''}" style="height:${h}px"></div>
                <div class="chart-label">${label}</div>
            </div>
        `);
    }
    container.innerHTML = bars.join('');
}

function _stepLabel(name) {
    const labels = {
        'init': '初始化',
        'face_analysis': '人脸分析',
        'view_animation': '视角动画',
        'expression_done': '表情完成',
        'expression_skipped': '表情跳过',
        'lip_sync_prepare': '唇形准备',
        'wav2lip': '唇形同步',
        'wav2lip_done': '唇形完成',
        'encode': '编码输出',
        'complete': '完成',
        'overall': '整体',
    };
    return labels[name] || name;
}

function _formatDuration(secs) {
    if (!secs || secs <= 0) return '--';
    if (secs < 60) return secs.toFixed(1) + 's';
    if (secs < 3600) return Math.floor(secs / 60) + 'm ' + Math.round(secs % 60) + 's';
    return Math.floor(secs / 3600) + 'h ' + Math.floor((secs % 3600) / 60) + 'm';
}

function _formatDate(isoStr) {
    if (!isoStr) return '--';
    try {
        const d = new Date(isoStr);
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
        if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
        return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    } catch {
        return isoStr;
    }
}

// Load analytics on page load
document.addEventListener('DOMContentLoaded', loadAnalytics);
