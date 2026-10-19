> **?? ki?m th? t?ch h?p:** xem [k?t qu? th?c t?, frontend v? c?ch m? b?n test](VALIDATION_V1.md). C?c ghi ch? ch?a ch?y d?ch v? th?t b?n d??i ph?n ?nh tr?ng th?i l?c t?o b?n v1; k?t qu? m?i nh?t n?m trong b?o c?o n?y.

# Nâng cấp v1: đa định dạng và đánh giá RAG

## Phạm vi đã triển khai

- PDF có chữ/bảng, DOCX, TXT, Markdown, CSV và XLSX.
- Nội dung giữ nguyên dấu câu; bảng được chia theo hàng, lặp lại tiêu đề cột.
- Lưu file gốc, hash theo người dùng, job bền vững trong MySQL, retry và chống nhân đôi vector.
- Chat kiểm tra quyền hội thoại/tài liệu, truy xuất chung trên tài liệu ready, trả sources và trace_id.
- Tin nhắn và trace được commit cùng giao dịch MySQL. Redis TTL watcher cũ đã tắt.
- Đánh giá offline: retrieval, nguồn trích dẫn, tốc độ, tỷ lệ lỗi; tùy chọn Groq chấm semantic.

OCR, đọc ảnh/biểu đồ và công cụ tính toán trên toàn bộ bảng chưa thuộc v1. XLSX đọc giá trị được lưu sẵn của công thức, không chạy Excel để tính lại. Bảng phức tạp, ô gộp, nhiều hàng tiêu đề vẫn cần kiểm tra thủ công.

## Cài đặt

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Đối chiếu `.env.example` với `.env` hiện tại. Tên biến Pinecone trong code là `PIPECONE_*` để tương thích dự án cũ. Index chunk cần có dimension 384 tương ứng embedding hiện tại. Không đổi model embedding mà tiếp tục dùng vector cũ.

### Database

Dùng MySQL 8. Với database mới, chạy `mysql.sql` trước. Với database hiện có, sao lưu và kiểm tra tên bảng trước khi nâng cấp. `chatbot.sql` cũ là SQL Server, không dùng cho luồng MySQL này.

```powershell
.\.venv\Scripts\python.exe -m src.config.migrate
```

Migration thêm Role nếu thiếu, ConversationDocuments, IngestionJobs và ChatTraces. Chạy lại được với schema tương ứng; nếu bảng liên kết cũ có bản ghi trùng thì cần xử lý trùng trước khi tạo unique key. MySQL DDL có thể tự commit nên backup vẫn cần thiết.

**Chưa chạy migration trên database được cấu hình trong `.env`.** Các file cũ không được lưu nguyên bản bởi pipeline trước; hãy tải lại để đưa vào luồng mới. Không tự gán tài liệu cũ cho hội thoại khi không có bằng chứng sở hữu/liên kết.

### Chạy hai tiến trình

```powershell
.\.venv\Scripts\python.exe -m src.app
.\.venv\Scripts\python.exe -m src.workers.ingestion
```

Hai lệnh chạy ở hai terminal. Web và mọi worker phải dùng cùng database và `DOCUMENT_STORAGE_DIR`. Khi deploy nhiều máy, mount cùng persistent volume. Không dùng ổ tạm của container để lưu originals. Worker khóa từng job bằng MySQL GET_LOCK trên connection riêng; kết nối chết sẽ giải phóng khóa để worker khác xử lý lại. Trong v1, polling tối đa 100 job mỗi lượt; tăng worker để xử lý song song, chưa phải hệ phân tán quy mô lớn.

## API

Tất cả API dưới đây yêu cầu Bearer access token.

- `POST /api/conversations/{id}/documents`: multipart `files` và tùy chọn `description`. Tối đa 10 file/request, 20 MiB/file, 50 MiB/request. Trả HTTP 202 và results gồm document_id, job_id, status. Endpoint cũ `/api/upload_pdf/{id}` là alias nhưng **đã chuyển từ đồng bộ 201 sang bất đồng bộ 202**; frontend phải cập nhật polling.
- `GET /api/documents/{id}/status`: queued, processing, ready hoặc failed; attempts và lỗi đã rút gọn.
- `POST /api/documents/{id}/retry`: đưa file failed vào hàng đợi lại.
- `GET /api/conversations/{id}/files`: có thêm filename và status. FileURL có thể null; chưa có API download original.
- `POST /api/chat`: giữ query_text, conversation_id, document_ids; thêm sources và trace_id trong response. Nếu không truyền document_ids, dùng tất cả tài liệu ready của hội thoại. Tài liệu chỉ định chưa ready trả 409; tài liệu không thuộc hội thoại trả 404. Nếu chỉ một số tài liệu ready, chế độ tự chọn dùng phần ready.
- `GET /api/chat/traces/{trace_id}`: chỉ chủ sở hữu đọc được câu hỏi, câu trả lời, retrieved, context thực tế và nguồn.

Giới hạn parser: PDF 500 trang, tối đa 20.000 blocks/chunks, file Office sau giải nén tối đa 100 MiB, XLSX tối đa 1.000 cột. TXT/Markdown/CSV dùng UTF-8. Bản đầu chia văn bản theo ký tự và điểm ngắt câu; chưa dùng tokenizer. Truy xuất top 8 chung, context tối đa 16.000 ký tự; chưa có reranker. Có nguồn trong response nghĩa là bằng chứng đã được cung cấp cho model, không bảo đảm mọi khẳng định đều đúng.

## Đánh giá

`src/evaluation/dataset.example.jsonl` là **mẫu minh họa 3 câu**, chưa phải bộ benchmark thực và chưa chứng minh chất lượng. Thay filename, trang/sheet/hàng, conversation_id, document_ids bằng dữ liệu test của bạn. Nên có 50–100 câu do người đọc tài liệu kiểm tra: text, bảng, nhiều tài liệu, hỏi tiếp và không có đáp án. Không dùng câu dùng để chỉnh prompt làm toàn bộ tập test cuối.

Prediction JSONL có id trùng dataset và các trường giống trace API:

```json
{
  "id": "text-01",
  "query": "Câu hỏi khớp dataset",
  "answer": "Đáp án [S1]",
  "retrieved": [
    { "filename": "a.pdf", "page": 1, "chunk_id": 12, "score": 0.8 }
  ],
  "sources": [{ "id": "S1", "filename": "a.pdf", "page": 1 }],
  "context": [{ "source": { "id": "S1" }, "text": "Bằng chứng" }],
  "latency_ms": 1250
}
```

Chấm dữ liệu đã thu thập, không gọi API:

```powershell
.\.venv\Scripts\python.exe -m src.evaluation.run --dataset evaluation-data/test.jsonl --predictions evaluation-data/predictions.jsonl --output evaluation-results/baseline
```

Tùy chọn `--replay-user 1` chạy chat thật bằng tài khoản sở hữu các hội thoại và ghi predictions. Lệnh gọi embedding/LLM, tốn API và ghi tin nhắn/trace; dùng tài khoản và hội thoại test riêng. Chuẩn bị lịch sử hội thoại giống nhau giữa các lần chạy; chạy lặp trên cùng hội thoại sẽ thay đổi context và làm lệch so sánh.

Thêm `--judge` để Groq chấm correctness, faithfulness, relevance và citation_accuracy theo rubric. Nội dung câu hỏi/đáp án/context được gửi cho Groq; đây là bộ chấm tự triển khai, **không phải RAGAS**. Kết quả là ước lượng cần human review. Khi judge lỗi, báo judge_error và số mẫu được chấm, không giả điểm 0 hay 1.

JSON và CSV được tạo cùng prefix output. JSON có overall, by_category và từng case:

- Precision@k: tỷ lệ chunk lấy ra khớp các nhãn bằng chứng; mẫu số là số chunk thực tế lấy ra, tối đa k.
- Recall@k: tỷ lệ nhãn bằng chứng tìm được. Nhãn theo filename/page/sheet/row; có thể thêm chunk_id nếu ID không đổi. Câu không có bằng chứng chuẩn nhận null.
- citation_id_validity chỉ kiểm tra ID nguồn tồn tại; không đồng nghĩa citation_accuracy về nội dung.
- p50/p95 trên latency_ms của prediction thành công, error_rate bao gồm prediction thiếu/lỗi.
- Metric semantic chưa chấm nhận null. Không có metric token/chi phí vì client hiện chưa thu usage.

Lưu báo cáo trước/sau cùng tập test, cấu hình model và lịch sử để so sánh. Chưa có baseline thực từ dịch vụ ngoài; không nên tuyên bố chất lượng tăng trước khi chạy benchmark. Chưa có tính năng tự so sánh hai báo cáo hay cổng chặn deploy theo ngưỡng.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test local dùng SQLite cho logic dữ liệu và mock dịch vụ ngoài. Cần kiểm thử staging MySQL thật cho migration, GET_LOCK, nhiều worker, upload/status/chat và lỗi mạng. Không chạy app cũ cùng app mới trên cùng database: app cũ vẫn có thể chạy Redis watcher.

File gốc được giữ lại ngay cả khi job failed để retry; v1 chưa có tác vụ thu gom original/vector mồ côi. Xóa hội thoại chỉ xóa dữ liệu hội thoại/trace và liên kết, không xóa tài liệu dùng chung hay vector tài liệu. API có thể xử lý nhiều file hơn trước nhưng chưa có số đo tải thực tế.
