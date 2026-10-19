# Kết nối frontend với backend v1

Workspace hiện chỉ có backend; chưa thể sửa giao diện của repository khác. Module `examples/frontend-client.mjs` dùng fetch thuần, có thể đưa vào frontend hiện có. Không chứa khóa Groq/Hugging Face/Pinecone; chỉ nhận access token của người dùng.

```javascript
import { createChatbotClient, renderSources } from './frontend-client.mjs';

const api = createChatbotClient({
  baseUrl: 'http://localhost:5000/api',
  getToken: () => authState.accessToken
});

const controller = new AbortController();
const upload = await api.uploadDocuments(conversationId, [...fileInput.files], {
  signal: controller.signal
});

// Hiển thị lỗi từng file ngay, kể cả khi request tổng thể trả 202.
const rejected = upload.results.filter(item => !item.success);
const accepted = upload.results.filter(item => item.success);
const statuses = await api.waitForDocuments(accepted.map(item => item.document_id), {
  signal: controller.signal,
  onProgress: items => updateDocumentStatuses(items)
});

const readyIds = statuses.filter(item => item.status === 'ready').map(item => item.document_id);
if (readyIds.length) {
  const reply = await api.sendMessage({ conversationId, text: question, documentIds: readyIds });
  answerElement.textContent = reply.response;
  renderSources(sourcesListElement, reply.sources);
}
```

- `queued`/`processing`: hiển thị đang xử lý; chưa chọn file đó để hỏi.
- `ready`: cho chọn file để chat.
- `failed`: hiển thị lỗi và nút retry; sau retry tiếp tục polling.
- 401: dùng luồng refresh token của frontend rồi gửi lại request; client mẫu không tự lưu/refresh token.
- 404: tài liệu/hội thoại không tồn tại hoặc không có quyền.
- 409: tài liệu được chọn chưa sẵn sàng; cập nhật trạng thái và thử lại sau.
- 413: giảm dung lượng/số file trong request.

Khi rời màn hình gọi `controller.abort()` để dừng polling phía client; tác vụ xử lý file trên server vẫn tiếp tục. Với câu trả lời Markdown, dùng renderer có sanitize; không đưa chuỗi từ model hoặc tên file vào innerHTML trực tiếp. Chưa có endpoint download original nên nguồn được hiển thị dạng tên file/trang/sheet/hàng.
