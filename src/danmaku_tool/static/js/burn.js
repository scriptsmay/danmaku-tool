/* 压制页面交互逻辑 */

async function submitTask() {
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
        // 跳转到任务详情页
        window.location.href = `/tasks/${data.task_id}`;
    } catch (e) {
        alert('提交失败: ' + e.message);
        btn.disabled = false;
        btn.textContent = '开始压制';
    }
}
