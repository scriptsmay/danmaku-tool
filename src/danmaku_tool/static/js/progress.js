/* SSE 进度监听通用模块 */

function watchProgress(taskId, callbacks) {
    /**
     * 监听任务进度。
     * callbacks: { onProgress(data), onDone(data), onError(data) }
     */
    const es = new EventSource(`/api/tasks/${taskId}/stream`);

    es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        if (callbacks.onProgress) callbacks.onProgress(data);
    });

    es.addEventListener('done', (e) => {
        const data = JSON.parse(e.data);
        es.close();
        if (callbacks.onDone) callbacks.onDone(data);
    });

    es.addEventListener('error', (e) => {
        // SSE error 事件没有 data
        es.close();
        if (callbacks.onError) callbacks.onError({ error: '连接断开' });
    });

    return es;
}
