/* 文件浏览器 JS */

let currentPath = '';
let selectedVideo = '';
let selectedAss = '';

async function browsePath(path) {
    const listEl = document.getElementById('browser-list');
    const breadcrumbEl = document.getElementById('browser-breadcrumb');
    listEl.innerHTML = '<div class="px-4 py-3 text-gray-400 text-sm">加载中...</div>';

    try {
        const url = path ? `/api/files/browse?path=${encodeURIComponent(path)}&filter_ext=.mp4,.mkv,.flv,.ts,.jsonl,.ass` : '/api/files/browse';
        const resp = await fetch(url);
        if (!resp.ok) throw new Error('请求失败');
        const data = await resp.json();
        currentPath = data.current;

        // 面包屑
        renderBreadcrumb(data.current, data.parent);

        // 文件列表
        if (!data.entries.length) {
            listEl.innerHTML = '<div class="px-4 py-3 text-gray-400 text-sm">空目录</div>';
            return;
        }

        listEl.innerHTML = data.entries.map(entry => {
            if (entry.is_dir) {
                return `
                    <div class="px-4 py-2 flex items-center hover:bg-gray-50 cursor-pointer" onclick="browsePath('${escapePath(entry.path)}')">
                        <span class="text-yellow-500 mr-2">📁</span>
                        <span class="text-sm text-gray-800">${entry.name}</span>
                    </div>`;
            } else {
                const ext = entry.ext || '';
                const isVideo = ['.mp4', '.mkv', '.flv', '.ts'].includes(ext);
                const isDanmaku = ['.jsonl', '.ass'].includes(ext);
                const sizeStr = entry.size ? formatFileSize(entry.size) : '';
                const selectBtn = isVideo
                    ? `<button onclick="selectFile('video', '${escapePath(entry.path)}')" class="px-2 py-0.5 text-xs bg-primary-100 text-primary-700 rounded hover:bg-primary-200">选择视频</button>`
                    : isDanmaku
                    ? `<button onclick="selectFile('ass', '${escapePath(entry.path)}')" class="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200">选择弹幕</button>`
                    : '';
                const icon = isVideo ? '🎬' : isDanmaku ? '📄' : '📃';
                return `
                    <div class="px-4 py-2 flex items-center justify-between hover:bg-gray-50">
                        <div class="flex items-center min-w-0">
                            <span class="mr-2">${icon}</span>
                            <span class="text-sm text-gray-800 truncate">${entry.name}</span>
                            <span class="text-xs text-gray-400 ml-2">${sizeStr}</span>
                        </div>
                        ${selectBtn}
                    </div>`;
            }
        }).join('');
    } catch (e) {
        listEl.innerHTML = '<div class="px-4 py-3 text-red-400 text-sm">加载失败: ' + e.message + '</div>';
    }
}

function renderBreadcrumb(current, parent) {
    const el = document.getElementById('browser-breadcrumb');
    let html = '<span class="cursor-pointer hover:text-primary-600" onclick="browsePath(\'\')">根目录</span>';
    if (current) {
        html += `<span class="text-gray-300 mx-1">/</span>`;
        html += `<span class="text-gray-800">${current}</span>`;
    }
    if (parent) {
        html += `<span class="ml-auto cursor-pointer hover:text-primary-600 text-xs" onclick="browsePath('${escapePath(parent)}')">⬆ 上级</span>`;
    }
    el.innerHTML = html;
}

function selectFile(type, path) {
    if (type === 'video') {
        selectedVideo = path;
        document.getElementById('video-path').value = path;
    } else {
        selectedAss = path;
        document.getElementById('ass-path').value = path;
    }
    // 选择任一文件后，只要有视频路径就尝试计算偏移
    if (selectedVideo) {
        calcOffset(selectedVideo);
    }
    updateSubmitButton();
}

function clearSelection(type) {
    if (type === 'video') {
        selectedVideo = '';
        document.getElementById('video-path').value = '';
        document.getElementById('offset-ms').value = 0;
        document.getElementById('offset-hint').textContent = '';
    } else {
        selectedAss = '';
        document.getElementById('ass-path').value = '';
    }
    updateSubmitButton();
}

async function calcOffset(videoPath) {
    const offsetInput = document.getElementById('offset-ms');
    const hintEl = document.getElementById('offset-hint');
    try {
        const resp = await fetch(`/api/files/calc-offset?video_path=${encodeURIComponent(videoPath)}`);
        if (!resp.ok) return;
        const data = await resp.json();
        offsetInput.value = data.offset_ms;
        hintEl.textContent = data.message || '';
        if (data.video_time) {
            hintEl.textContent += ` (${data.video_time})`;
        }
    } catch (e) {
        hintEl.textContent = '自动计算失败，请手动输入';
    }
}

function updateSubmitButton() {
    const ready = !!(selectedVideo && selectedAss);
    document.getElementById('btn-submit').disabled = !ready;
    const testBtn = document.getElementById('btn-test');
    if (testBtn) testBtn.disabled = !ready;
}

function escapePath(p) {
    return p.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function formatFileSize(bytes) {
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
    return bytes.toFixed(1) + ' ' + units[i];
}

// 页面加载时浏览根目录
document.addEventListener('DOMContentLoaded', () => browsePath(''));
