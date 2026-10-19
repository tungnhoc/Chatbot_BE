# Kết quả kiểm thử tích hợp v1 — 19/10/2026

## Môi trường và phạm vi

Đã chạy MySQL 8 thật, Pinecone thật và Groq thật. Database và namespace vector riêng được tạo cho từng lượt test; không migration hoặc sửa dữ liệu database gốc. Không thay đổi `.env` của backend/frontend. Các tiến trình kiểm thử đã dừng sau khi chạy.

Hugging Face hosted embedding trả HTTP 402 do hết credit. Đã bổ sung backend embedding CPU tùy chọn `local-onnx`, dùng bản quantized 384 chiều của paraphrase-multilingual-MiniLM-L12-v2, pin revision trong code. Không tự chuyển embedding của dữ liệu đang có: local bắt buộc namespace riêng và cần ingest lại. Model đã được cache trong `storage/models`.

Model Groq mặc định cũ không có trong danh sách khả dụng của tài khoản tại thời điểm kiểm tra. Lượt test dùng `openai/gpt-oss-20b`, temperature 0. Giá trị mặc định của code cũng đã cập nhật; model có thể cấu hình qua GROQ_MODEL.

## Kết quả

| Hạng mục | Kết quả |
|---|---|
| Migration MySQL chạy hai lần | Đạt trên database test |
| Upload PDF, DOCX, TXT, MD, CSV, XLSX | Cả 6 nhận 202 và chuyển ready |
| Hai worker chạy đồng thời | Xử lý hoàn tất các tài liệu test |
| Upload lại cùng nội dung | Trả lại document_id hiện có |
| Smoke chat ban đầu | 8/8 request thành công sau sửa lỗi Unicode log Windows |
| Benchmark đồng thời ban đầu | 44/52 thành công; 8 lỗi do quota Groq |
| Chạy lại riêng 8 câu lỗi với nhịp chậm | 52/52 có prediction thành công sau phục hồi |
| Recall@8 | 1,00 trên 50 câu có nhãn bằng chứng sau phục hồi |
| Precision@8 | Khoảng 0,607 trên 50 câu có nhãn sau phục hồi |
| ID trích dẫn hợp lệ | 1,00 trên 50 câu có trích dẫn |
| Đối chiếu số nguyên với đáp án fixture | 50/50 khớp |
| Hai câu không có đáp án | Cả hai trả lời tài liệu không cung cấp thông tin |
| LLM judge | Correctness/faithfulness/relevance trung bình 1,00 trên 52 câu; citation accuracy 1,00 trên 50 câu |
| Độ trễ sau ghép kết quả phục hồi | p50 khoảng 4,63 giây; p95 khoảng 9,35 giây |

Đây là **52 câu giả lập đơn giản**, không phải tài liệu nghiệp vụ của người dùng. Bộ sinh dữ liệu và đáp án xác định nằm ở `src/evaluation/fixtures.py`. Judge dùng cùng model với chatbot, do đó có thiên lệch; điểm 1,00 không chứng minh chất lượng production. Numeric fact match chỉ kiểm tra số nguyên mong đợi xuất hiện, không thay cho đánh giá ngữ nghĩa hoặc phép tính tổng quát.

Không so sánh chất lượng với phiên bản cũ vì chưa có baseline tương đương trước nâng cấp. Độ trễ sau phục hồi là tập kết quả trộn giữa hai chế độ tải; không phải benchmark đồng thời sạch. Báo cáo gốc có tỷ lệ lỗi 15,38% được giữ nguyên. Cần benchmark lại dưới tải mục tiêu và quota phù hợp trước khi cam kết SLA.

## Frontend

Đã sửa trực tiếp repository `D:\chatbot-FE\chatbot-frontend`:

- Giữ HTTP 202 của upload, polling trạng thái, hiển thị lỗi và retry.
- Hỗ trợ đúng 6 định dạng; bỏ lựa chọn `.doc` cũ chưa được backend hỗ trợ.
- Sửa URL proxy lấy danh sách file, thêm proxy status/retry.
- Hiển thị nguồn trong câu trả lời, giữ nguồn khi tải lại lịch sử.
- Dừng polling khi đổi hội thoại; không đưa file chưa ready vào request chat.
- Danh sách document_ids rỗng có nghĩa bỏ chọn tài liệu; bỏ hẳn trường này mới tự chọn tài liệu ready của hội thoại.

TypeScript `tsc --noEmit --incremental false` đạt. `npm run build` exit 0, compile và generate pages thành công, nhưng bước ESLint có lỗi cấu hình có sẵn: Next 14 gọi các option không còn được ESLint 10 hỗ trợ. Chưa chứng nhận lint sạch; không tắt lint để che lỗi. Chưa kiểm thử trực quan bằng trình duyệt.

Đã chạy Next production server tạm thời và kiểm tra HTTP qua proxy thật: 9/9 đạt (auth status, upload 202, ready, list file, từ chối tài khoản khác, từ chối retry file ready, nguồn chat, nguồn/trace trong history).

## Báo cáo và chạy lại

Artifact trong workspace, không chứa khóa API/mật khẩu:

- `storage/integration/v1-benchmark/dataset.jsonl`: 52 câu, đáp án và nhãn nguồn.
- `storage/integration/v1-benchmark/report.json`: báo cáo lượt đồng thời đầu tiên, gồm lỗi quota.
- `storage/integration/v1-benchmark/repaired_report.json`: báo cáo sau retry có ghi rõ recovered_cases.
- `storage/integration/v1-benchmark/predictions.jsonl` và `repaired_predictions.jsonl`: câu trả lời, retrieval, context và usage thực tế.
- `storage/integration/v1-benchmark/frontend-smoke.json`: kết quả 9 kiểm tra proxy.
- `storage/frontend-v1/originals`: bản sao các file frontend đã chỉnh trước khi áp dụng.

Chạy lại toàn bộ bằng một thư mục output mới, sẽ tạo database và namespace test mới và phát sinh API usage:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe -m src.evaluation.integration --output storage/integration/run-new --limit 0 --judge
```

Muốn mở ứng dụng để tự thử, dùng database test đã tạo:

```powershell
# Terminal backend tại D:\Chatbot1\chatbot
.\.venv\Scripts\python.exe -m src.evaluation.serve storage/integration/v1-benchmark

# Terminal frontend tại D:\chatbot-FE\chatbot-frontend
npm.cmd start
```

Mở http://localhost:3000, đăng ký một tài khoản test của bạn rồi upload tài liệu. Tài khoản trong database gốc không được sao chép sang database test. File .env frontend hiện trỏ backend tới 127.0.0.1:5000, phù hợp lệnh trên. Không chạy lệnh serve khi đã có dịch vụ khác chiếm cổng 5000.

Database test, originals và namespace được giữ để kiểm tra lại; không tự xóa dữ liệu hay vector. Cần đưa tài liệu nghiệp vụ thật vào một bộ test được con người kiểm tra, sửa lint frontend và kiểm thử trình duyệt trước khi chuyển cấu hình sang database chính.
