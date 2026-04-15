CREATE TABLE Users (
    UserID INT AUTO_INCREMENT PRIMARY KEY,
    UserName VARCHAR(100) NOT NULL,
    Email VARCHAR(255) UNIQUE,
    PasswordHash VARCHAR(255),
    CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Documents (
    DocumentID INT AUTO_INCREMENT PRIMARY KEY,
    FileName VARCHAR(255) NOT NULL,
    FilePath VARCHAR(500),
    FileType VARCHAR(50),         -- pdf, txt, docx...
    UploadedBy INT,
    UploadedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
    FileSizeMB FLOAT,
    Description VARCHAR(500),

    CONSTRAINT FK_Documents_Users
        FOREIGN KEY (UploadedBy)
        REFERENCES Users(UserID)
        ON DELETE SET NULL
);
CREATE TABLE DocumentChunks (
    ChunkID INT AUTO_INCREMENT PRIMARY KEY,
    DocumentID INT NOT NULL,
    ChunkText LONGTEXT,
    Embedding LONGBLOB,            -- vector embedding
    Metadata JSON,                 -- MySQL hỗ trợ JSON native
    CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT FK_DocumentChunks_Documents
        FOREIGN KEY (DocumentID)
        REFERENCES Documents(DocumentID)
        ON DELETE CASCADE
);

CREATE TABLE Conversations (
    ConversationID INT AUTO_INCREMENT PRIMARY KEY,
    UserID INT NOT NULL,
    Title VARCHAR(255),
    Summary LONGTEXT,
    CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT FK_Conversations_Users
        FOREIGN KEY (UserID)
        REFERENCES Users(UserID)
        ON DELETE CASCADE
);

CREATE TABLE Messages (
    MessageID INT AUTO_INCREMENT PRIMARY KEY,
    ConversationID INT NOT NULL,
    Role VARCHAR(50),              -- 'user' | 'assistant'
    Text LONGTEXT,
    Summary LONGTEXT,
    Embedding LONGBLOB,
    Timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT FK_Messages_Conversations
        FOREIGN KEY (ConversationID)
        REFERENCES Conversations(ConversationID)
        ON DELETE CASCADE
);

CREATE TABLE VectorMemorySummary (
    SummaryID INT AUTO_INCREMENT PRIMARY KEY,
    ConversationID INT NOT NULL,
    SummaryText LONGTEXT,
    Embedding LONGBLOB,
    CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT FK_VectorMemorySummary_Conversations
        FOREIGN KEY (ConversationID)
        REFERENCES Conversations(ConversationID)
        ON DELETE CASCADE
);

CREATE TABLE TokenBlacklist (
    id INT AUTO_INCREMENT PRIMARY KEY,
    jti VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);


