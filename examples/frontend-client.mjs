/** Framework-independent client for the v1 backend. Never embeds API/provider keys. */
export function createChatbotClient({ baseUrl = '/api', getToken, fetchImpl = fetch }) {
  async function request(path, { signal, body, method = 'GET' } = {}) {
    const token = await getToken();
    const headers = { Authorization: `Bearer ${token}` };
    if (body && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    const response = await fetchImpl(`${baseUrl.replace(/\/$/, '')}${path}`, { method, headers, body, signal });
    const value = await response.json();
    if (!response.ok) {
      const error = new Error(value.error || value.message || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return value;
  }

  async function uploadDocuments(conversationId, files, { description = '', signal } = {}) {
    if (!files.length || files.length > 10) throw new Error('Choose between 1 and 10 files');
    const body = new FormData();
    for (const file of files) body.append('files', file);
    body.append('description', description);
    // HTTP 202 means accepted, not ready for chat yet. Inspect each result.success.
    return request(`/conversations/${conversationId}/documents`, { method: 'POST', body, signal });
  }

  async function waitForDocuments(ids, { onProgress = () => {}, signal, intervalMs = 1500, timeoutMs = 240000 } = {}) {
    const started = Date.now();
    while (true) {
      signal?.throwIfAborted();
      const statuses = await Promise.all(ids.map(id => request(`/documents/${id}/status`, { signal })));
      onProgress(statuses);
      if (statuses.every(item => ['ready', 'failed'].includes(item.status))) return statuses;
      if (Date.now() - started >= timeoutMs) throw new Error('Timed out waiting for documents; processing may still be running');
      await new Promise((resolve, reject) => {
        const abort = () => { clearTimeout(timer); reject(signal.reason || new Error('Aborted')); };
        const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, intervalMs);
        signal?.addEventListener('abort', abort, { once: true });
      });
    }
  }

  return {
    uploadDocuments, waitForDocuments,
    listDocuments: (id, options) => request(`/conversations/${id}/files`, options),
    retryDocument: (id, { signal } = {}) => request(`/documents/${id}/retry`, { method: 'POST', signal }),
    getTrace: (id, options) => request(`/chat/traces/${encodeURIComponent(id)}`, options),
    sendMessage: ({ conversationId, text, documentIds = [], signal }) => request('/chat', {
      method: 'POST', signal, body: { conversation_id: conversationId, query_text: text, document_ids: documentIds }
    })
  };
}

/** Render source labels safely. Backend v1 does not expose public original-file URLs. */
export function renderSources(container, sources) {
  container.replaceChildren();
  for (const source of sources) {
    const label = document.createElement('li');
    label.textContent = [`[${source.id}] ${source.filename}`,
      source.page ? `trang ${source.page}` : null,
      source.sheet ? `sheet ${source.sheet}` : null,
      source.row ? `hàng ${source.row}` : null].filter(Boolean).join(' — ');
    container.append(label);
  }
}
