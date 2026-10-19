# Schema bắt buộc và sửa lỗi thiếu ConversationDocuments

## Kết luận từ repository

Backend hiện tại yêu cầu 10 bảng, đúng chữ hoa/thường trên MySQL Linux:

| Bảng | Nguồn định nghĩa |
|---|---|
| `users` | `src/models/Users.py`, `mysql.sql`; class Python vẫn là `User` |
| `Documents` | Model cùng tên, `mysql.sql` |
| `DocumentChunks` | Model cùng tên, `mysql.sql` |
| `Conversations` | Model cùng tên, `mysql.sql` |
| `Messages` | Model cùng tên, `mysql.sql` |
| `VectorMemorySummary` | Model cùng tên, `mysql.sql` |
| `TokenBlacklist` | Model cùng tên, `mysql.sql` |
| `ConversationDocuments` | `migrations/001_multiformat.sql`; dùng SQL viết tay, không có ORM model |
| `IngestionJobs` | `migrations/001_multiformat.sql`; dùng SQL viết tay, không có ORM model |
| `ChatTraces` | `migrations/001_multiformat.sql` và cột bổ sung trong `src/config/migrate.py`; không có ORM model |

`mysql.sql` là schema nền, chưa có ba bảng cuối và chưa thêm `users.Role`. `chatbot.sql` là script SQL Server cũ (IDENTITY, NVARCHAR, GO), không áp dụng lên Railway MySQL. Các cột Summary/Embedding thừa trong script nền được giữ, không bắt xóa để khớp ORM.

Lỗi 1146 chứng minh tên `ConversationDocuments` không truy cập được trong database `railway`; có thể thiếu bảng hoặc bảng có tên khác chữ hoa/thường. Nó phù hợp việc nâng cấp 001 chưa được áp dụng đầy đủ, nhưng không chứng minh trạng thái của IngestionJobs/ChatTraces. Repository chưa có bảng ghi lịch sử migration nên không thể kết luận chính xác migration nào từng chạy chỉ từ lỗi này. Chưa kết nối production để kiểm tra.

## Định nghĩa chính xác

`ConversationDocuments`:

- `ConversationID INT NOT NULL`, `DocumentID INT NOT NULL`: khóa chính ghép.
- `FileURL VARCHAR(500) NULL`.
- `UploadedAt DATETIME DEFAULT CURRENT_TIMESTAMP`.
- `IsDeleted BOOLEAN NOT NULL DEFAULT FALSE`.
- FK ConversationID → Conversations.ConversationID, DocumentID → Documents.DocumentID; đều ON DELETE CASCADE.
- MySQL tạo index hỗ trợ FK DocumentID; PK ghép hỗ trợ tra cứu theo ConversationID. Schema cũ có ID PK riêng cũng hợp lệ nếu có UNIQUE(ConversationID,DocumentID).

`IngestionJobs`:

- `JobID CHAR(32)` PK.
- `DocumentID INT NOT NULL UNIQUE`, FK → Documents.DocumentID ON DELETE CASCADE.
- `UserID INT NOT NULL`, FK → **users.UserID** ON DELETE CASCADE.
- `ContentHash CHAR(64) NOT NULL`, `PipelineVersion VARCHAR(50) NOT NULL`.
- `Status VARCHAR(20) NOT NULL DEFAULT 'queued'`.
- `Attempts INT NOT NULL DEFAULT 0`, `Error VARCHAR(500) NULL`.
- `NextAttemptAt`, `CreatedAt`, `UpdatedAt`: DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP.
- UNIQUE(UserID,ContentHash,PipelineVersion); index (Status,NextAttemptAt) cho worker polling.

`ChatTraces` cũng bắt buộc vì cả chat lẫn tải lịch sử đều dùng bảng này:

- TraceID CHAR(32) PK, UserID INT NOT NULL, ConversationID INT NOT NULL, Payload JSON NOT NULL.
- CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP.
- AssistantMessageID INT NULL UNIQUE, phục vụ JOIN với Messages.MessageID khi tải lịch sử.
- FK ConversationID → Conversations.ConversationID ON DELETE CASCADE.
- Code/migration cũ không khai báo FK cho UserID hoặc AssistantMessageID; migration mới giữ đúng định nghĩa đó.

## Bản sửa bổ sung

`migrations/002_runtime_tables.sql` chứa CREATE TABLE IF NOT EXISTS cho ba bảng cuối, dùng `users` chữ thường và đầy đủ AssistantMessageID ngay khi tạo ChatTraces. Không chỉnh `001_multiformat.sql` đã có; không DROP, RENAME hoặc xóa dữ liệu.

`src/config/schema_v1.py` là lệnh audit và áp dụng bổ sung có chủ đích. Audit kiểm tra tên bảng, các cột bắt buộc, PK, UNIQUE, FK và queue index. Cho phép cột legacy thừa; không xác minh mọi thuộc tính kiểu dữ liệu/default của các cột hiện có. Nếu bảng hiện có sai cấu trúc, sai case, thiếu FK/index, lệnh dừng để kiểm tra thay vì tự đoán cách sửa. Riêng hai cột đã có định nghĩa rõ là users.Role và ChatTraces.AssistantMessageID được thêm nếu thiếu. Không thêm lại nếu đã có.

## Áp dụng lên Railway từ Render

Đưa code mới lên GitHub và deploy backend trước để có module mới. Sao lưu Railway bằng công cụ backup/dump phù hợp trước khi chạy DDL. Trong Render Shell của đúng service backend (đã cấu hình DATABASE_URL hoặc MYSQL_* trỏ Railway), chạy:

```bash
# Chỉ đọc; trả schema_ready=false và exit 1 nếu còn thiếu/sai.
python -m src.config.schema_v1 --check

# Chỉ chạy sau khi đã đọc kết quả audit và sao lưu.
python -m src.config.schema_v1 --apply

# Xác minh; phải trả schema_ready=true và issues=[].
python -m src.config.schema_v1 --check
```

Nếu Render không có Shell, dùng terminal local với cùng các biến Railway public trong môi trường của terminal đó. Không gửi mật khẩu/URL có credentials vào chat hoặc commit. Không đổi host sang railway.internal khi kết nối từ Render/local.

--apply tạo bảng chỉ khi chưa có, giữ bảng/dữ liệu đang tồn tại; chạy lại trên schema hợp lệ không phát sinh DDL. Nếu bị dừng giữa chừng, MySQL DDL có thể đã auto-commit; kiểm tra lại trước khi chạy tiếp. Không tự khởi tạo bảng nền hoặc sửa tên bảng bị khác case. Cần quyền CREATE/ALTER/REFERENCES và các cột FK ở bảng cha tương thích kiểu INT, khóa unique/PK và engine hỗ trợ FK.

## Kiểm tra sau áp dụng

Chạy trên Railway bằng SQL client, không cần xem nội dung dữ liệu người dùng:

```sql
SHOW CREATE TABLE users;
SHOW CREATE TABLE ConversationDocuments;
SHOW CREATE TABLE IngestionJobs;
SHOW CREATE TABLE ChatTraces;
SHOW INDEX FROM ConversationDocuments;
SHOW INDEX FROM IngestionJobs;
SHOW INDEX FROM ChatTraces;

-- Kiểm tra câu JOIN đúng mà không đọc dữ liệu tài liệu:
SELECT cd.DocumentID
FROM ConversationDocuments cd
JOIN Documents d ON d.DocumentID = cd.DocumentID
JOIN IngestionJobs j ON j.DocumentID = d.DocumentID
LIMIT 0;
```

Sau đó thử tạo hội thoại, lấy danh sách file, upload, chạy worker và chat bằng tài khoản test. Migration không tự tạo job/liên kết cho tài liệu cũ vì code trước chưa lưu đủ nguồn để suy ra; cần upload lại các file đó. Không chỉ sửa tên SQL để bỏ qua bảng thiếu: backend thật sự cần cả ba bảng cho upload, queue và history.
