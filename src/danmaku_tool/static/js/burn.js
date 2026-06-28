/* 压制页面交互逻辑 */

// 初始化：页面加载后更新输出路径 placeholder + 加载字体列表
async function initBurnPage() {
    const config = await getHealthConfig();
    const outputDir = config.output_dir || 'DanmakuOutput';
    const suffix = config.suffix || '_danmaku';
    const placeholder = document.getElementById('output-path');
    if (placeholder && !placeholder.value) {
        placeholder.placeholder = outputDir + '/{文件名}' + suffix;
    }
    await loadFonts();
}

document.addEventListener('DOMContentLoaded', initBurnPage);

// 从 /api/health 获取配置（output_dir, suffix），缓存一次
let _healthConfig = null;
async function getHealthConfig() {
    if (_healthConfig) return _healthConfig;
    try {
        const resp = await fetch('/api/health');
        const data = await resp.json();
        _healthConfig = data.config || {};
        return _healthConfig;
    } catch {
        return {};
    }
}

// ── 字体选择 ──

async function loadFonts() {
    try {
        const resp = await fetch('/api/fonts');
        const data = await resp.json();
        const select = document.getElementById('font-family');
        if (!select) return;
        select.innerHTML = '';
        const current = data.current || '';
        const list = data.fonts || [];

        // 如果当前字体不在列表中，放在最前面
        if (current && !list.includes(current)) {
            const opt = document.createElement('option');
            opt.value = current;
            opt.textContent = current + ' (未检测到)';
            opt.selected = true;
            select.appendChild(opt);
        }

        for (const name of list) {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            if (name === current) opt.selected = true;
            select.appendChild(opt);
        }

        if (!select.options.length) {
            const opt = document.createElement('option');
            opt.value = current || 'Noto Sans CJK SC';
            opt.textContent = current || 'Noto Sans CJK SC';
            opt.selected = true;
            select.appendChild(opt);
        }

        // 绑定 change 事件
        select.addEventListener('change', onFontChange);
    } catch {
        const select = document.getElementById('font-family');
        if (select) select.innerHTML = '<option value="">加载失败</option>';
    }
}

async function onFontChange(e) {
    const fontName = e.target.value;
    const hint = document.getElementById('font-hint');
    if (!fontName || !hint) return;
    hint.textContent = '保存中...';
    hint.className = 'text-xs text-gray-400';
    try {
        const resp = await fetch('/api/settings/font', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ font_family: fontName }),
        });
        const data = await resp.json();
        if (data.persisted) {
            hint.textContent = '已保存';
            hint.className = 'text-xs text-green-500';
        } else {
            hint.textContent = '已应用（重启后失效）';
            hint.className = 'text-xs text-amber-500';
        }
    } catch {
        hint.textContent = '保存失败';
        hint.className = 'text-xs text-red-500';
    }
}

// 自动填入输出路径
async function autoFillOutputPath() {
    const videoPath = document.getElementById('video-path').value;
    if (!videoPath) {
        alert('请先选择视频文件');
        return;
    }
    const config = await getHealthConfig();
    const outputDir = config.output_dir || 'DanmakuOutput';
    const suffix = config.suffix || '_danmaku';

    // 从视频路径提取文件名，加上后缀
    const parts = videoPath.replace(/\\/g, '/').split('/');
    const filename = parts[parts.length - 1];
    const dotIdx = filename.lastIndexOf('.');
    const stem = dotIdx > 0 ? filename.substring(0, dotIdx) : filename;
    const outputName = stem + suffix + '.mp4';

    // 输出目录 + 原文件名所在子目录名（保留层级）
    const videoDir = parts.slice(0, -1).join('/');
    const outputPath = outputDir + '/' + outputName;

    document.getElementById('output-path').value = outputPath;
}

// 显示确认弹窗，mode: 'burn' 或 'test'
let _confirmMode = 'burn';
async function showConfirm(mode = 'burn') {
    _confirmMode = mode;
    const videoPath = document.getElementById('video-path').value;
    const assPath = document.getElementById('ass-path').value;
    const fps = document.getElementById('fps').value;
    const offsetMs = document.getElementById('offset-ms').value;
    const outputPath = document.getElementById('output-path').value || '（自动生成）';
    const encoder = document.querySelector('input[name="encoder"]:checked')?.value || 'auto';

    const encoderLabels = { nvenc: 'NVENC (GPU)', cpu: 'CPU (libx264)', auto: '自动' };
    const encoderLabel = encoderLabels[encoder] || encoder;
    const fontName = document.getElementById('font-family')?.selectedOptions[0]?.textContent || '默认';

    const videoName = videoPath.split(/[/\\]/).pop();
    const assName = assPath.split(/[/\\]/).pop();

    // 缓存信息
    const config = await getHealthConfig();
    const cacheLine = config.cache_enabled
        ? `<div class="flex"><span class="w-24 text-gray-500 shrink-0">本地缓存</span><span class="text-gray-900 text-xs font-mono">${config.cache_dir}</span></div>`
        : '';

    const body = document.getElementById('confirm-body');
    const titleEl = document.getElementById('confirm-title');
    const actionBtn = document.getElementById('confirm-action-btn');

    if (mode === 'test') {
        titleEl.textContent = '确认压制测试参数';
        actionBtn.textContent = '开始测试';
        actionBtn.onclick = submitTestBurn;
        actionBtn.className = 'px-6 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm font-medium';
        body.innerHTML = `
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">模式</span><span class="text-amber-600 font-medium">压制测试（仅编码前 60 秒）</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">视频</span><span class="text-gray-900 break-all">${videoName}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">弹幕</span><span class="text-gray-900 break-all">${assName}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">字体</span><span class="text-gray-900">${fontName}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">编码器</span><span class="text-gray-900">${encoderLabel}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">帧率</span><span class="text-gray-900">${fps} fps</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">偏移量</span><span class="text-gray-900 font-mono">${offsetMs} ms</span></div>
            ${cacheLine}
        `;
    } else {
        titleEl.textContent = '确认压制参数';
        actionBtn.textContent = '确认开始';
        actionBtn.onclick = submitTask;
        actionBtn.className = 'px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium';
        body.innerHTML = `
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">视频</span><span class="text-gray-900 break-all">${videoName}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">弹幕</span><span class="text-gray-900 break-all">${assName}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">字体</span><span class="text-gray-900">${fontName}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">编码器</span><span class="text-gray-900">${encoderLabel}</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">帧率</span><span class="text-gray-900">${fps} fps</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">偏移量</span><span class="text-gray-900 font-mono">${offsetMs} ms</span></div>
            <div class="flex"><span class="w-24 text-gray-500 shrink-0">输出</span><span class="text-gray-900 break-all text-xs">${outputPath}</span></div>
            ${cacheLine}
        `;
    }

    document.getElementById('confirm-modal').classList.remove('hidden');
}

function hideConfirm() {
    document.getElementById('confirm-modal').classList.add('hidden');
}

async function submitTask() {
    hideConfirm();

    const videoPath = document.getElementById('video-path').value;
    const assPath = document.getElementById('ass-path').value;
    const fps = parseInt(document.getElementById('fps').value) || 30;
    const outputPath = document.getElementById('output-path').value || null;
    const encoder = document.querySelector('input[name="encoder"]:checked')?.value || 'auto';

    if (!videoPath || !assPath) {
        alert('请选择视频文件和弹幕文件');
        return;
    }

    const btn = document.getElementById('btn-submit');
    btn.disabled = true;
    btn.textContent = '提交中...';

    try {
        const body = {
            video_path: videoPath,
            ass_path: assPath,
            encoder: encoder,
            fps: fps,
            offset_ms: parseInt(document.getElementById('offset-ms').value) || 0,
        };
        if (outputPath) body.output_path = outputPath;

        const resp = await fetch('/api/burn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '提交失败');
        }

        const data = await resp.json();
        window.location.href = `/tasks/${data.task_id}`;
    } catch (e) {
        alert('提交失败: ' + e.message);
        btn.disabled = false;
        btn.textContent = '开始压制';
    }
}

// ── 压制测试 ──

let _testSSE = null;

function _getTestParams() {
    const videoPath = document.getElementById('video-path').value;
    const assPath = document.getElementById('ass-path').value;
    const fps = parseInt(document.getElementById('fps').value) || 30;
    const encoder = document.querySelector('input[name="encoder"]:checked')?.value || 'auto';
    const offsetMs = parseInt(document.getElementById('offset-ms').value) || 0;
    return { video_path: videoPath, ass_path: assPath, encoder, fps, offset_ms: offsetMs };
}

function _showTestSection() {
    const section = document.getElementById('test-section');
    section.classList.remove('hidden');
    // 重置状态
    document.getElementById('test-progress-bar').style.width = '0%';
    document.getElementById('test-progress-percent').textContent = '0%';
    document.getElementById('test-progress-time').textContent = '';
    document.getElementById('test-progress-speed').textContent = '';
    document.getElementById('test-progress-status').textContent = '排队中';
    document.getElementById('test-error').classList.add('hidden');
    document.getElementById('test-preview-wrap').classList.add('hidden');
    document.getElementById('test-progress-wrap').classList.remove('hidden');
    // 滚动到测试区域
    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function _updateTestProgress(data) {
    document.getElementById('test-progress-wrap').classList.remove('hidden');
    document.getElementById('test-progress-bar').style.width = data.progress + '%';
    document.getElementById('test-progress-percent').textContent = data.progress.toFixed(1) + '%';
    document.getElementById('test-progress-speed').textContent = data.speed || '';
    const statusMap = { queued: '排队中', processing: '压制中', completed: '已完成', failed: '失败' };
    document.getElementById('test-progress-status').textContent = statusMap[data.status] || data.status;
}

function _showTestError(msg) {
    document.getElementById('test-progress-wrap').classList.add('hidden');
    const errEl = document.getElementById('test-error');
    errEl.textContent = msg;
    errEl.classList.remove('hidden');
}

function _showTestPreview(taskId, outputSize) {
    document.getElementById('test-progress-wrap').classList.add('hidden');
    document.getElementById('test-progress-status').textContent = '已完成';

    // 显示文件大小
    if (outputSize) {
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = outputSize, i = 0;
        while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
        document.getElementById('test-output-size').textContent = size.toFixed(1) + ' ' + units[i];
    }

    // 设置视频源并显示
    const player = document.getElementById('test-video-player');
    player.src = `/api/burn/test/${taskId}/video`;
    document.getElementById('test-preview-wrap').classList.remove('hidden');
}

async function submitTestBurn() {
    hideConfirm();
    const params = _getTestParams();
    if (!params.video_path || !params.ass_path) {
        alert('请选择视频文件和弹幕文件');
        return;
    }

    const btn = document.getElementById('btn-test');
    btn.disabled = true;
    btn.textContent = '提交中...';

    // 关闭之前的 SSE
    if (_testSSE) {
        _testSSE.close();
        _testSSE = null;
    }

    try {
        const resp = await fetch('/api/burn/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '提交失败');
        }

        const data = await resp.json();
        const taskId = data.task_id;

        btn.textContent = '测试中...';
        _showTestSection();

        // 监听 SSE 进度
        _testSSE = watchProgress(taskId, {
            onProgress(progressData) {
                _updateTestProgress(progressData);
            },
            onDone(doneData) {
                _testSSE = null;
                btn.disabled = false;
                btn.textContent = '压制测试（60s）';
                if (doneData.status === 'completed' && !doneData.error) {
                    _showTestPreview(taskId, doneData.output_size);
                } else if (doneData.status === 'cancelled') {
                    _showTestError('测试任务已取消');
                } else {
                    _showTestError(doneData.error || '压制失败');
                }
            },
            onError() {
                _testSSE = null;
                btn.disabled = false;
                btn.textContent = '压制测试（60s）';
                _showTestError('连接断开，请刷新页面');
            },
        });

    } catch (e) {
        alert('测试提交失败: ' + e.message);
        btn.disabled = false;
        btn.textContent = '压制测试（60s）';
    }
}
