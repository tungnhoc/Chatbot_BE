-- Supplemental MySQL schema sourced from 001_multiformat.sql and migrate.py.
-- Does not modify existing tables. Use schema_v1 --apply for preflight/verification.
CREATE TABLE IF NOT EXISTS ConversationDocuments (
    ConversationID INT NOT NULL,
    DocumentID INT NOT NULL,
    FileURL VARCHAR(500) NULL,
    UploadedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
    IsDeleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (ConversationID, DocumentID),
    FOREIGN KEY (ConversationID) REFERENCES Conversations(ConversationID) ON DELETE CASCADE,
    FOREIGN KEY (DocumentID) REFERENCES Documents(DocumentID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS IngestionJobs (
    JobID CHAR(32) PRIMARY KEY,
    DocumentID INT NOT NULL UNIQUE,
    UserID INT NOT NULL,
    ContentHash CHAR(64) NOT NULL,
    PipelineVersion VARCHAR(50) NOT NULL,
    Status VARCHAR(20) NOT NULL DEFAULT 'queued',
    Attempts INT NOT NULL DEFAULT 0,
    Error VARCHAR(500) NULL,
    NextAttemptAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_content (UserID, ContentHash, PipelineVersion),
    KEY ix_job_queue (Status, NextAttemptAt),
    FOREIGN KEY (DocumentID) REFERENCES Documents(DocumentID) ON DELETE CASCADE,
    FOREIGN KEY (UserID) REFERENCES users(UserID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ChatTraces (
    TraceID CHAR(32) PRIMARY KEY,
    UserID INT NOT NULL,
    ConversationID INT NOT NULL,
    Payload JSON NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AssistantMessageID INT NULL UNIQUE,
    FOREIGN KEY (ConversationID) REFERENCES Conversations(ConversationID) ON DELETE CASCADE
);
