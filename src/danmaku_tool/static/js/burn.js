/* 压制页面交互逻辑 */

// 初始化：页面加载后更新输出路径 placeholder
async function initBurnPage() {
    const config = await getHealthConfig();
    const outputDir = config.output_dir || 'DanmakuOutput';
    const suffix = config.suffix || '_danmaku';
    const placeholder = document.getElementById('output-path');
    if (placeholder && !placeholder.value) {
        placeholder.placeholder = outputDir + '/{文件名}' + suffix + '.mp4';
    }
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
    const ext = dotIdx > 0 ? filename.substring(dotIdx) : '.mp4';
    const outputName = stem + suffix + ext;

    // 输出目录 + 原文件名所在子目录名（保留层级）
    const videoDir = parts.slice(0, -1).join('/');
    const outputPath = outputDir + '/' + outputName;

    document.getElementById('output-path').value = outputPath;
}

// 显示确认弹窗
async function showConfirm() {
    const videoPath = document.getElementById('video-path').value;
    const assPath = document.getElementById('ass-path').value;
    const fps = document.getElementById('fps').value;
    const offsetMs = document.getElementById('offset-ms').value;
    const outputPath = document.getElementById('output-path').value || '（自动生成）';
    const encoder = document.querySelector('input[name="encoder"]:checked')?.value || 'auto';

    const encoderLabels = { nvenc: 'NVENC (GPU)', cpu: 'CPU (libx264)', auto: '自动' };
    const encoderLabel = encoderLabels[encoder] || encoder;

    const videoName = videoPath.split(/[/\\]/).pop();
    const assName = assPath.split(/[/\\]/).pop();

    const body = document.getElementById('confirm-body');
    body.innerHTML = `
        <div class="flex"><span class="w-24 text-gray-500 shrink-0">视频</span><span class="text-gray-900 break-all">${videoName}</span></div>
        <div class="flex"><span class="w-24 text-gray-500 shrink-0">弹幕</span><span class="text-gray-900 break-all">${assName}</span></div>
        <div class="flex"><span class="w-24 text-gray-500 shrink-0">编码器</span><span class="text-gray-900">${encoderLabel}</span></div>
        <div class="flex"><span class="w-24 text-gray-500 shrink-0">帧率</span><span class="text-gray-900">${fps} fps</span></div>
        <div class="flex"><span class="w-24 text-gray-500 shrink-0">偏移量</span><span class="text-gray-900 font-mono">${offsetMs} ms</span></div>
        <div class="flex"><span class="w-24 text-gray-500 shrink-0">输出</span><span class="text-gray-900 break-all text-xs">${outputPath}</span></div>
    `;

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
