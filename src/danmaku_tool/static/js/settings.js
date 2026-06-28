/**
 * 全局设置页面逻辑
 */

const DEFAULTS = {
    font_family: "Noto Sans CJK SC",
    font_size: 36,
    opacity: 0.88,
    outline_width: 1,
    max_per_second: 10,
};

let currentSettings = {};
let dirty = false;

// ── 初始化 ──

async function init() {
    await loadSettings();
    await loadFonts();
    attachListeners();
}

async function loadSettings() {
    try {
        const res = await fetch("/api/settings");
        currentSettings = await res.json();
        applyToForm(currentSettings);
    } catch (e) {
        console.error("加载设置失败:", e);
    }
}

async function loadFonts() {
    try {
        const res = await fetch("/api/fonts");
        const data = await res.json();
        const select = document.getElementById("setting-font-family");
        select.innerHTML = "";
        const fonts = data.fonts || [];
        if (fonts.length === 0 && currentSettings.font_family) {
            const opt = document.createElement("option");
            opt.value = currentSettings.font_family;
            opt.textContent = currentSettings.font_family;
            select.appendChild(opt);
        } else {
            for (const font of fonts) {
                const opt = document.createElement("option");
                opt.value = font;
                opt.textContent = font;
                select.appendChild(opt);
            }
        }
        if (currentSettings.font_family) {
            select.value = currentSettings.font_family;
        }
    } catch (e) {
        console.error("加载字体列表失败:", e);
    }
}

function applyToForm(s) {
    document.getElementById("setting-font-family").value = s.font_family || "";
    document.getElementById("setting-font-size").value = s.font_size ?? 36;
    document.getElementById("setting-opacity").value = s.opacity ?? 0.88;
    document.getElementById("setting-opacity-range").value = s.opacity ?? 0.88;
    document.getElementById("setting-outline-width").value = s.outline_width ?? 1;
    document.getElementById("setting-max-per-second").value = s.max_per_second ?? 15;
}

// ── 事件监听 ──

function attachListeners() {
    const ids = [
        "setting-font-family",
        "setting-font-size",
        "setting-opacity",
        "setting-opacity-range",
        "setting-outline-width",
        "setting-max-per-second",
    ];
    for (const id of ids) {
        const el = document.getElementById(id);
        el.addEventListener("input", () => {
            dirty = true;
            document.getElementById("btn-save").disabled = false;
            document.getElementById("save-status").textContent = "未保存";
            document.getElementById("save-status").className = "text-sm text-amber-500";
            // 同步 opacity 滑块和输入框
            if (id === "setting-opacity-range") {
                document.getElementById("setting-opacity").value = el.value;
            } else if (id === "setting-opacity") {
                document.getElementById("setting-opacity-range").value = el.value;
            }
        });
    }
}

// ── 保存 ──

async function saveSettings() {
    const payload = {
        font_family: document.getElementById("setting-font-family").value,
        font_size: parseInt(document.getElementById("setting-font-size").value, 10),
        opacity: parseFloat(document.getElementById("setting-opacity").value),
        outline_width: parseInt(document.getElementById("setting-outline-width").value, 10),
        max_per_second: parseInt(document.getElementById("setting-max-per-second").value, 10),
    };

    if (!payload.font_family.trim()) {
        const status = document.getElementById("save-status");
        status.textContent = "字体名称不能为空";
        status.className = "text-sm text-red-500";
        return;
    }

    const btn = document.getElementById("btn-save");
    const status = document.getElementById("save-status");
    btn.disabled = true;
    btn.textContent = "保存中...";
    status.textContent = "";

    try {
        const res = await fetch("/api/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const data = await res.json();
            status.textContent = data.detail || "保存失败";
            status.className = "text-sm text-red-500";
        } else {
            const data = await res.json();
            currentSettings = { ...currentSettings, ...payload };
            dirty = false;
            status.textContent = data.persisted ? "已保存并持久化" : "已保存（内存）";
            status.className = "text-sm text-green-600";
            document.getElementById("font-status").textContent = "";
        }
    } catch (e) {
        status.textContent = "保存失败: " + e.message;
        status.className = "text-sm text-red-500";
    } finally {
        btn.textContent = "保存设置";
        btn.disabled = !dirty;
    }
}

// ── 恢复默认 ──

function resetToDefaults() {
    applyToForm(DEFAULTS);
    dirty = true;
    document.getElementById("btn-save").disabled = false;
    document.getElementById("save-status").textContent = "未保存（已恢复默认值）";
    document.getElementById("save-status").className = "text-sm text-amber-500";
}

// 页面离开前提醒
window.addEventListener("beforeunload", (e) => {
    if (dirty) {
        e.preventDefault();
        e.returnValue = "";
    }
});

document.addEventListener("DOMContentLoaded", init);
