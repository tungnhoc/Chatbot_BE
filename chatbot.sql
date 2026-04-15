
--CREATE DATABASE Chatbot;
GO
USE Chatbot;
GO
-- ============================
-- 🧍 BẢNG NGƯỜI DÙNG (Users)
-- ============================

CREATE TABLE Users (
    UserID INT IDENTITY(1,1) PRIMARY KEY,
    UserName NVARCHAR(100) NOT NULL,
    Email NVARCHAR(255) UNIQUE,
    PasswordHash NVARCHAR(255),
    CreatedAt DATETIME DEFAULT GETDATE()
);


-- ============================
-- 📄 BẢNG TÀI LIỆU (Documents)
-- ============================



CREATE TABLE Documents (
    DocumentID INT IDENTITY(1,1) PRIMARY KEY,
    FileName NVARCHAR(255) NOT NULL,
    FilePath NVARCHAR(500),
    FileType NVARCHAR(50),       -- ví dụ: pdf, txt, docx
    UploadedBy INT,              -- khóa ngoại trỏ đến Users
    UploadedAt DATETIME DEFAULT GETDATE(),
    FileSizeMB FLOAT,            -- kích thước file (tùy chọn)
    Description NVARCHAR(500),   -- mô tả ngắn
    FOREIGN KEY (UploadedBy) REFERENCES Users(UserID)
);


-- ============================
-- 📚 BẢNG CHIA NHỎ TÀI LIỆU (DocumentChunks)
-- ============================
CREATE TABLE DocumentChunks (
    ChunkID INT IDENTITY(1,1) PRIMARY KEY,
    DocumentID INT NOT NULL,         -- liên kết đến Documents
    ChunkText NVARCHAR(MAX),         -- nội dung đoạn text
    Embedding VARBINARY(MAX),        -- vector embedding (mảng float -> binary)
    Metadata NVARCHAR(MAX),          -- JSON: {"page": 3, "offset": 1024}
    CreatedAt DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (DocumentID) REFERENCES Documents(DocumentID)
);

-- ============================
-- 💬 BẢNG HỘI THOẠI (Conversations)
CREATE TABLE Conversations (
    ConversationID INT IDENTITY(1,1) PRIMARY KEY,
    UserID INT NOT NULL,             -- người tạo cuộc hội thoại
    Title NVARCHAR(255),             -- tiêu đề tóm tắt
    Summary NVARCHAR(MAX),           -- tóm tắt toàn bộ nội dung hội thoại
    CreatedAt DATETIME DEFAULT GETDATE(),
    UpdatedAt DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (UserID) REFERENCES Users(UserID)
);
GO

-- ============================
-- 💭 BẢNG TIN NHẮN (Messages)
-- ============================
CREATE TABLE Messages (
    MessageID INT IDENTITY(1,1) PRIMARY KEY,
    ConversationID INT NOT NULL,
    Role NVARCHAR(50),               -- 'user' hoặc 'assistant'
    Text NVARCHAR(MAX),              -- nội dung tin nhắn
    Summary NVARCHAR(MAX),           -- tóm tắt ngắn
    Embedding VARBINARY(MAX),        -- embedding của câu nói
    Timestamp DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ConversationID) REFERENCES Conversations(ConversationID)
);



CREATE TABLE VectorMemorySummary (
    SummaryID INT IDENTITY(1,1) PRIMARY KEY,
    ConversationID INT NOT NULL,     -- Liên kết với bảng Conversations
    SummaryText NVARCHAR(MAX),       -- Tóm tắt nội dung hội thoại
    Embedding VARBINARY(MAX),        -- Embedding của bản tóm tắt
    CreatedAt DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (ConversationID) REFERENCES Conversations(ConversationID)
);


CREATE TABLE TokenBlacklist (
    id INT IDENTITY(1,1) PRIMARY KEY,
    jti NVARCHAR(255) NOT NULL UNIQUE,   -- JWT ID
    created_at DATETIME2 DEFAULT SYSDATETIME()
);

CREATE TABLE ConversationDocuments (
    ID INT IDENTITY(1,1) PRIMARY KEY,

    ConversationID INT NOT NULL,
    DocumentID INT NOT NULL,

    UploadedBy INT NULL,
    UploadedAt DATETIME2 DEFAULT SYSDATETIME(),

    FileURL NVARCHAR(500),
    IsDeleted BIT DEFAULT 0,

    CONSTRAINT FK_ConversationDocuments_Conversations
        FOREIGN KEY (ConversationID)
        REFERENCES Conversations(ConversationID)
        ON DELETE CASCADE,

    CONSTRAINT FK_ConversationDocuments_Documents
        FOREIGN KEY (DocumentID)
        REFERENCES Documents(DocumentID)
        ON DELETE CASCADE
);

