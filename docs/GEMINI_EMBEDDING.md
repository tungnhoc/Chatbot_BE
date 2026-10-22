# Chuyển embedding sang Gemini

Backend hỗ trợ Gemini qua REST, không cần cài thêm SDK. Gemini thay phần tạo vector; mô hình trả lời và MySQL giữ nguyên. Thay embedding không tự bổ sung OCR hoặc đọc hình ảnh.

## Cấu hình

1. Tạo API key tại https://aistudio.google.com/apikey. Chỉ lưu key ở backend, không đưa vào biến `NEXT_PUBLIC_*` hoặc commit Git.
2. Tạo **index Pinecone mới** tên `pdf-gemini-768`, dimension **768**, metric **cosine**. Namespace mới không thể thay dimension của index cũ 384 chiều. Giữ index cũ để bảo toàn dữ liệu.
3. Đặt các biến sau trong Render → backend → Environment (hoặc `.env` khi chạy local):

```dotenv
EMBEDDING_BACKEND=gemini
GEMINI_API_KEY=<API key của bạn>
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_EMBEDDING_DIMENSION=768
PIPECONE_PDF_CHUNK_INDEX=pdf-gemini-768
PINECONE_NAMESPACE=gemini-v1
INGESTION_WORKER_MODE=embedded
```

`PIPECONE_PDF_CHUNK_INDEX` là cách viết hiện có trong code. Giữ `PIPECONE_API_KEY`, cấu hình Groq, JWT và MySQL. Nếu dùng các hàm summary cũ, index `PIPECONE_PDF_SUMMARY_INDEX` cũng phải có dimension tương ứng.

4. Deploy phiên bản code có hỗ trợ Gemini. Build command: `pip install -r requirements.txt`; start command: `gunicorn -c gunicorn.conf.py src.app:app`.
5. Tạo cuộc hội thoại mới, tải lại tài liệu và đợi trạng thái `ready` rồi đặt câu hỏi. Vector cũ không tương thích với mô hình mới. Không cần migration MySQL cho thay đổi này.

Backend kiểm tra dimension trước khi gọi embedding, tạo fingerprint theo model/dimension/index/namespace để không tái sử dụng job cũ, và từ chối dùng tài liệu có embedding thuộc cấu hình cũ. Không xóa hoặc chuyển dữ liệu production tự động.

## Kiểm tra

Nếu Console không có lựa chọn vector index, từ terminal tại thư mục dự án chạy:

```powershell
.\.venv\Scripts\python.exe create_gemini_index.py
```

Script đọc `PIPECONE_API_KEY` từ `.env`, tạo index `pdf-gemini-768` (AWS us-east-1, dense 768, cosine), không xóa index cũ. Index đã tồn tại sẽ được kiểm tra trước khi tái sử dụng. Nếu bị giới hạn số index, script báo lỗi và không tự xóa dữ liệu hoặc nâng cấp gói.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Các kiểm tra dùng mock và SQLite, không gọi Gemini thật hoặc database production. Sau deploy, thử một TXT nhỏ: upload → job `ready` → hỏi một dữ kiện có trong file → kiểm tra câu trả lời và trích dẫn. Nếu lỗi, xem lỗi job và log backend; không công khai API key.

Gemini Embedding 2 được gọi riêng cho từng chunk để nhận một vector cho mỗi chunk. Tài liệu lớn có thể chậm hoặc gặp quota. Free tier và giới hạn phụ thuộc chính sách, tài khoản và khu vực; xem https://ai.google.dev/gemini-api/docs/pricing và https://ai.google.dev/gemini-api/docs/rate-limits. Backend có retry giới hạn cho HTTP 429/5xx và lỗi kết nối.

Tài liệu API: https://ai.google.dev/gemini-api/docs/embeddings. Có thể chọn `gemini-embedding-001` nếu tài khoản hỗ trợ; khi đổi model, dùng index/namespace riêng và tải lại tài liệu.
