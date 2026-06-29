/**
 * 批量压制页面逻辑
 */

let selectedSessionId = null;
let sessions = [];

// ── 初始化 ──

async function init() {
    await loadSessions();
}

// ── 加载会话列表 ──

async function loadSessions() {
    const container = document.getElementById("session-list");
    container.innerHTML = '<div class="text-sm text-gray-400 py-4 text-center">加载中...</div>';

    try {
        const res = await fetch("/api/sessions");
        if (!res.ok) {
            const data = await res.json();
            container.innerHTML = `<div class="text-sm text-red-500 py-4 text-center">${data.detail || "加载失败"}</div>`;
            return;
        }

        const data = await res.json();
        sessions = data.sessions || [];

        if (sessions.length === 0) {
            container.innerHTML = '<div class="text-sm text-gray-400 py-4 text-center">暂无可用会话</div>';
            hideActionUI();
            return;
        }

        renderSessions(sessions);
    } catch (e) {
        container.innerHTML = `<div class="text-sm text-red-500 py-4 text-center">加载失败: ${e.message}</div>`;
        hideActionUI();
    }
}

function renderSessions(list) {
    const container = document.getElementById("session-list");
    container.innerHTML = "";

    for (const s of list) {
        const card = document.createElement("div");
        card.id = `session-${s.session_id}`;
        card.className = "border border-gray-200 rounded-lg p-4 cursor-pointer hover:border-primary-400 transition-colors";
        card.onclick = () => selectSession(s.session_id);

        const sizeStr = formatSize(s.total_size);
        const timeStr = s.created_at ? formatTime(s.created_at) : "-";
        const danmakuBadge = s.has_danmaku
            ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">有弹幕</span>'
            : '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500">无弹幕</span>';

        const fileList = s.video_files.slice(0, 3).join(", ") + (s.video_files.length > 3 ? ` ... 等 ${s.video_files.length} 个` : "");

        card.innerHTML = `
            <div class="flex items-center justify-between mb-2">
                <span class="font-medium text-gray-900">${s.session_id}</span>
                ${danmakuBadge}
            </div>
            <div class="flex items-center space-x-4 text-xs text-gray-500">
                <span>${s.video_count} 个视频</span>
                <span>${sizeStr}</span>
                <span>${timeStr}</span>
            </div>
            <div class="text-xs text-gray-400 mt-1 truncate">${fileList}</div>
        `;

        container.appendChild(card);
    }
}

// ── 选择会话 ──

function selectSession(sessionId) {
    // 取消之前的选中
    if (selectedSessionId) {
        const prev = document.getElementById(`session-${selectedSessionId}`);
        if (prev) {
            prev.className = "border border-gray-200 rounded-lg p-4 cursor-pointer hover:border-primary-400 transition-colors";
        }
    }

    if (selectedSessionId === sessionId) {
        // 再次点击取消选中
        selectedSessionId = null;
        hideActionUI();
        return;
    }

    selectedSessionId = sessionId;
    const card = document.getElementById(`session-${sessionId}`);
    if (card) {
        card.className = "border-2 border-primary-500 rounded-lg p-4 cursor-pointer bg-primary-50 transition-colors";
    }

    showActionUI();
}

function showActionUI() {
    document.getElementById("params-section").classList.remove("hidden");
    document.getElementById("action-section").classList.remove("hidden");
    document.getElementById("btn-batch-burn").disabled = false;
    document.getElementById("btn-ass-only").disabled = false;
    hideResult();
}

function hideActionUI() {
    document.getElementById("params-section").classList.add("hidden");
    document.getElementById("action-section").classList.add("hidden");
    hideResult();

    // 清除选中状态
    if (selectedSessionId) {
        const prev = document.getElementById(`session-${selectedSessionId}`);
        if (prev) {
            prev.className = "border border-gray-200 rounded-lg p-4 cursor-pointer hover:border-primary-400 transition-colors";
        }
        selectedSessionId = null;
    }
}

// ── 批量压制 ──

async function submitBatchBurn() {
    if (!selectedSessionId) return;

    const encoder = document.querySelector('input[name="encoder"]:checked')?.value || "auto";
    const fps = parseInt(document.getElementById("fps").value, 10) || 30;

    const btn = document.getElementById("btn-batch-burn");
    btn.disabled = true;
    btn.textContent = "提交中...";

    try {
        const res = await fetch("/api/burn/session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: selectedSessionId,
                encoder: encoder,
                fps: fps,
            }),
        });

        const data = await res.json();
        if (!res.ok) {
            showResult("提交失败", `<div class="text-red-600">${data.detail || "未知错误"}</div>`);
            return;
        }

        let html = `<div class="mb-2">已创建 <strong>${data.video_count}</strong> 个压制任务</div>`;
        html += '<div class="space-y-1">';
        for (const tid of data.task_ids) {
            html += `<a href="/tasks/${tid}" class="block text-primary-600 hover:text-primary-800 font-mono text-xs">${tid}</a>`;
        }
        html += "</div>";
        html += '<div class="mt-3"><a href="/" class="text-primary-600 hover:text-primary-800 text-sm">→ 查看任务列表</a></div>';

        showResult("批量压制已提交", html);
    } catch (e) {
        showResult("提交失败", `<div class="text-red-600">${e.message}</div>`);
    } finally {
        btn.disabled = false;
        btn.textContent = "批量压制";
    }
}

// ── 仅生成 ASS ──

async function submitAssOnly() {
    if (!selectedSessionId) return;

    const btn = document.getElementById("btn-ass-only");
    btn.disabled = true;
    btn.textContent = "生成中...";

    try {
        const res = await fetch("/api/ass/generate-session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: selectedSessionId }),
        });

        const data = await res.json();
        if (!res.ok) {
            showResult("生成失败", `<div class="text-red-600">${data.detail || "未知错误"}</div>`);
            return;
        }

        const files = data.generated_files || [];
        let html = `<div class="mb-2"><strong>生成成功</strong> — ${files.length} 个 ASS 文件</div>`;
        html += `<div class="text-gray-600 mb-2">弹幕总条数: <span class="font-mono">${data.danmaku_count}</span></div>`;
        if (files.length > 0) {
            html += '<div class="space-y-1">';
            for (const f of files) {
                const name = f.split(/[\\/]/).pop();
                html += `<div class="font-mono text-xs text-gray-600 break-all">${name}</div>`;
            }
            html += "</div>";
        }
        showResult("ASS 字幕生成", html);
    } catch (e) {
        showResult("生成失败", `<div class="text-red-600">${e.message}</div>`);
    } finally {
        btn.disabled = false;
        btn.textContent = "仅生成 ASS";
    }
}

// ── 结果显示 ──

function showResult(title, bodyHtml) {
    const section = document.getElementById("result-section");
    document.getElementById("result-title").textContent = title;
    document.getElementById("result-body").innerHTML = bodyHtml;
    section.classList.remove("hidden");
}

function hideResult() {
    document.getElementById("result-section").classList.add("hidden");
}

// ── 启动 ──

document.addEventListener("DOMContentLoaded", init);
