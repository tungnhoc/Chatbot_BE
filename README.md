# RAG PDF Chatbot Backend

Đây là repository backend cho dự án **RAG-based PDF Chatbot**, được xây dựng bằng **Python** và **Flask**. Hệ thống sử dụng công nghệ Retrieval-Augmented Generation (RAG) (Sinh văn bản tăng cường truy xuất) để cho phép người dùng tương tác thông minh với các tài liệu PDF đã tải lên.

Hệ thống được tích hợp với các công cụ hiện đại như **Groq** (Mô hình ngôn ngữ lớn - LLM), **Pinecone** (Cơ sở dữ liệu Vector), **MySQL/Supabase** (Cơ sở dữ liệu quan hệ), và **Upstash Redis** (Bộ nhớ đệm và xử lý tác vụ nền). Ngoài ra, hệ thống còn tích hợp một mô hình Học máy (Machine Learning) để đánh giá độ mạnh của mật khẩu nhằm tăng cường bảo mật trong quá trình đăng ký của người dùng.

## 🚀 Các Tính Năng Chính

- **Xác thực JWT (JWT Authentication)**: Các chức năng đăng ký, đăng nhập, làm mới token và đăng xuất an toàn, bao gồm cả cơ chế thu hồi token (token blacklisting).
- **Mô Hình Học Máy Đánh Giá Mật Khẩu**: Tích hợp một mô hình ML tuỳ chỉnh được huấn luyện để đánh giá và bắt buộc độ mạnh của mật khẩu khi người dùng đăng ký (được tích hợp trong `user_service`).
- **Retrieval-Augmented Generation (RAG)**: Xử lý các tài liệu PDF được tải lên, chia nhỏ văn bản (chunking) và tạo các vector nhúng (embeddings) để lưu trữ trong Pinecone.
- **Chat Thông Minh**: Sử dụng Groq LLM để tạo ra các câu trả lời nhận biết được ngữ cảnh, dựa trên các đoạn tài liệu liên quan nhất được trích xuất từ cơ sở dữ liệu vector.
- **Quản Lý Cuộc Trò Chuyện**: Tạo, đổi tên, xoá và hiển thị danh sách các cuộc trò chuyện, cùng với toàn bộ lịch sử tin nhắn và quản lý file.
- **Tích hợp Redis**: Sử dụng Upstash Redis cho các luồng xử lý chạy nền (background threads) và quản lý trạng thái.

## 🛠️ Công Nghệ Sử Dụng

- **Framework**: Flask, Gunicorn
- **Cơ sở dữ liệu**: MySQL (PyMySQL, SQLAlchemy), Supabase
- **Cơ sở dữ liệu Vector**: Pinecone
- **LLM**: Groq API
- **Bộ nhớ đệm / Messaging**: Upstash Redis
- **Xác thực**: Flask-JWT-Extended
- **Học máy (Machine Learning)**: Scikit-Learn (Phân loại độ mạnh mật khẩu)
- **Xử lý PDF**: PyPDF2
- **Xử lý ngôn ngữ tự nhiên (NLP)**: NLTK
- **Xác thực dữ liệu**: Pydantic

## 📂 Cấu Trúc Dự Án

```
chatbot/
├── .env                  # Các biến môi trường (không được lưu trên git)
├── requirements.txt      # Các thư viện Python cần thiết
├── chatbot.sql           # Schema của cơ sở dữ liệu
├── mysql.sql             # Scripts riêng cho MySQL
├── src/
│   ├── app.py            # File khởi chạy ứng dụng
│   ├── config/           # Cấu hình DB và các API của bên thứ 3
│   ├── llm/              # Tích hợp LLM và quản lý prompt (Groq)
│   ├── machine_learning/ # Jupyter notebooks và models xử lý mật khẩu
│   ├── models/           # Các model SQLAlchemy ORM (Users, Conversations, v.v.)
│   ├── routes/           # Các Flask Blueprints (Auth, Chat, Upload)
│   ├── schema/           # Pydantic schemas để validate request/response
│   ├── services/         # Logic xử lý cốt lõi (Auth, RAG, Chat)
│   └── utils/            # Các hàm hỗ trợ (JWT manager, Redis listener, xử lý PDF)
```

## ⚙️ Cài Đặt & Khởi Chạy

1. **Clone repository:**
   ```bash
   git clone <repository_url>
   cd chatbot
   ```

2. **Tạo môi trường ảo (khuyến nghị):**
   ```bash
   python -m venv .venv
   # Dành cho Windows
   .venv\Scripts\activate
   # Dành cho Linux/Mac
   source .venv/bin/activate
   ```

3. **Cài đặt các thư viện cần thiết:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Biến môi trường:**
   Tạo một file `.env` ở thư mục gốc và thêm các cấu hình cần thiết như sau:
   ```env
   # Flask App
   PORT=5000
   FLASK_JWT_SECRET_KEY=your_jwt_secret_key

   # Database (MySQL / Supabase)
   DATABASE_URL=your_mysql_database_url

   # Pinecone
   PINECONE_API_KEY=your_pinecone_api_key
   PINECONE_ENVIRONMENT=your_pinecone_env
   PINECONE_INDEX_NAME=your_index_name

   # Groq
   GROQ_API_KEY=your_groq_api_key

   # Upstash Redis
   REDIS_URL=your_upstash_redis_url
   ```

5. **Khởi tạo cơ sở dữ liệu:**
   Chạy các đoạn script SQL được cung cấp (`chatbot.sql` hoặc `mysql.sql`) trong cơ sở dữ liệu của bạn để tạo các bảng cần thiết (Users, Conversations, Messages, ConversationDocuments, v.v.).

6. **Chạy Ứng Dụng:**
   ```bash
   python -m src.app
   ```
   Server sẽ khởi chạy tại địa chỉ `http://0.0.0.0:5000`.

## 🔌 Các API Endpoints

### Xác thực / Authentication (`/api`)
- `POST /register`: Đăng ký người dùng mới (có tích hợp kiểm tra mật khẩu bằng ML).
- `POST /login`: Xác thực và nhận Access & Refresh JWTs.
- `POST /refresh`: Tạo một access token mới.
- `POST /logout`: Đăng xuất và đưa token hiện tại vào blacklist.

### Chat & Cuộc Trò Chuyện (`/api`)
- `GET /conversations`: Hiển thị danh sách các cuộc trò chuyện của người dùng đã đăng nhập.
- `POST /conversations/new`: Tạo một cuộc trò chuyện mới.
- `GET /conversations/<id>/history`: Lấy lịch sử chat (có phân trang).
- `GET /conversations/<id>/files`: Hiển thị danh sách các file liên quan tới cuộc trò chuyện.
- `PUT /conversations/<id>`: Đổi tên một cuộc trò chuyện.
- `DELETE /conversations/<id>`: Xóa một cuộc trò chuyện và dữ liệu vector bộ nhớ đi kèm.
- `POST /chat`: Gửi một tin nhắn và nhận phản hồi từ AI bằng cơ chế RAG.

### Upload Tài Liệu (`/api`)
- `POST /upload`: Tải lên tài liệu PDF, trích xuất văn bản, tạo vector nhúng và lưu vào Pinecone.

## 🚀 Triển Khai (Deployment)

Dự án này được cấu hình để có thể dễ dàng triển khai trên các nền tảng như **Railway**, **Render** hoặc **Heroku**. 
Dự án sử dụng `gunicorn` làm HTTP server (WSGI) cho môi trường production:
```bash
gunicorn -w 4 -b 0.0.0.0:$PORT src.app:app
```

## 📝 Giấy Phép (License)
Dự án này được thực hiện với mục đích giáo dục và phục vụ cho portfolio.
