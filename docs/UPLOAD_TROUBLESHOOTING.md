# Sửa upload chờ mãi và chữ tiếng Việt bị hỏng

## Thay đổi trong code

- Các chuỗi giao diện đã được khôi phục đúng UTF-8: Đang chờ xử lý, Đang xử lý, Nguồn tham khảo, Kiểm tra lại và thông báo upload. Có regression test để tránh các chuỗi dấu hỏi quay lại.
- Khi có NEXT_PUBLIC_API_URL, frontend gửi multipart trực tiếp từ browser đến backend, dùng Bearer token hiện có. Không chuyển file qua Vercel Function. Khi biến này chưa đặt, vẫn dùng proxy cũ. Cả hai định dạng response `results` (backend) và `uploaded` (proxy) đều được hỗ trợ.
- Polling có thông báo chờ lâu, timeout rõ ràng và dừng khi đổi hội thoại. File failed/error không còn hiển thị dấu tích xanh.
- Worker nhúng khởi động sau khi Gunicorn fork web worker, qua `gunicorn.conf.py`; không khởi động khi chỉ import Flask app hoặc chạy unit test. Khóa GET_LOCK hiện có ngăn hai worker xử lý cùng một job.
- Lỗi hết credit, sai credential, thiếu thư viện và mất original có thông báo riêng, không trả provider payload hoặc đường dẫn file riêng tư cho client.
- Upload lại cùng nội dung sẽ phục hồi original đã mất và đưa job failed về queued, giữ document ID/chunk ID để không nhân đôi vector.

Ảnh trạng thái queued không đủ để chứng minh lỗi ở parser PDF. Code cũ chỉ có hàng đợi và command worker riêng; command web `gunicorn src.app:app` không tự chạy ingestion. Vì vậy web service có thể nhận file nhưng không có ai xử lý job. Thay đổi này giải quyết khoảng trống khởi động đó cho một web service.

## Render: một web service, một replica

Sau khi push code và deploy backend, đặt Start Command rõ ràng:

```bash
gunicorn -c gunicorn.conf.py src.app:app
```

Environment:

```env
INGESTION_WORKER_MODE=embedded
```

Để `DOCUMENT_STORAGE_DIR` trỏ cùng một thư mục trong service. Embedded worker và HTTP worker cùng máy nên đọc được file vừa upload. Không cần chạy thêm background worker riêng trong chế độ này. Khi khởi động, log phải có `Embedded document ingestion worker started` (có thể tùy cấu hình logging INFO); quan trọng là status đi từ queued sang processing rồi ready/failed.

**Storage tạm có thể mất khi deploy/restart.** Dùng persistent disk nếu gói hosting hỗ trợ và đặt DOCUMENT_STORAGE_DIR tới đường dẫn mount thực tế. Nếu không có persistent storage, có thể phải upload lại file bị mất. Thay đổi này chưa bổ sung object storage và không bảo đảm giữ original qua restart. Không nhân bản web service sang nhiều replica mà vẫn dùng original chỉ lưu trên ổ local từng replica.

Nếu chọn worker service riêng: đặt `INGESTION_WORKER_MODE=external` trên web, chạy `python -m src.workers.ingestion` riêng và cung cấp filesystem bền vững được chia sẻ thật sự. Cùng DATABASE_URL nhưng mỗi service có một ổ local riêng là chưa đủ.

## Vercel

Redeploy frontend sau khi có code mới. Giữ:

```env
NEXT_PUBLIC_API_URL=https://chatbot-be-imn0.onrender.com
```

Trình duyệt sẽ gửi file tới `/api/conversations/{id}/documents` trên Render. Request Authorization được CORS của Flask cho phép; preflight đã có test local. NEXT_PUBLIC_API_URL là URL public, không chứa credential hay khóa API.

[Vercel giới hạn body của Function ở 4,5 MB](https://vercel.com/docs/functions/limitations); upload trực tiếp tránh giới hạn của proxy này. Backend hiện vẫn giới hạn 20 MiB/file và 50 MiB/request, parser cũng có giới hạn riêng. Cấu hình server/proxy khác vẫn có thể giới hạn thấp hơn.

## Xác minh sau deploy

Frontend hiện chặn gửi khi file đang failed/error hoặc chưa xác minh, không chỉ khi queued/processing. Backend cũng từ chối trường hợp tài liệu có liên kết nhưng chưa có ingestion job hoặc chưa ready. Nếu vector truy xuất không trả được context cho file đã chọn, backend trả 503 thay vì gọi model với context rỗng. Các lỗi này không được ghi thành câu trả lời AI thành công. Người dùng cần xử lý lại file trước khi hỏi; đây không phải bằng chứng rằng tài liệu thiếu thông tin.

1. Upload một TXT/PDF nhỏ bằng tài khoản test, giữ Network mở. Request upload phải tới Render và trả 202.
2. Poll `/api/documents/{id}/status` phải đổi queued → processing → ready hoặc failed kèm nguyên nhân.
3. Khi ready, nút gửi câu hỏi được mở và nguồn trích dẫn hiển thị đúng tiếng Việt.
4. Thử file lớn hơn 4,5 MB nhưng nhỏ hơn 20 MiB để kiểm tra đường upload trực tiếp.
5. Nếu failed báo hết hạn mức embedding, kiểm tra credit Hugging Face; không đổi model/namespace của dữ liệu cũ một cách tự động. Local ONNX cần dependencies trong requirements-local.txt và namespace riêng như tài liệu v1.
6. Nếu original đã mất, chọn lại file để upload. Nút thử lại đơn thuần không tái tạo được file từ ổ đã mất.

Không có migration mới cho bản sửa này. Không tự chạy hoặc chỉnh sửa dữ liệu production trong quá trình sửa. Test backend dùng SQLite/mocks; chưa xác minh các request có đăng nhập trên deployment Render/Vercel của người dùng.

Nguồn tham khảo hooks: [Gunicorn settings](https://docs.gunicorn.org/en/stable/settings.html).
