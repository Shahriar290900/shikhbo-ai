-- Shikhbo NeonDB schema
-- Run once: psql $DATABASE_URL -f init_db.sql

CREATE TABLE IF NOT EXISTS users (
    uid        SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    email      VARCHAR(255) UNIQUE NOT NULL,
    password   VARCHAR(255),                 -- NULL for Google-only accounts
    google_id  VARCHAR(255),                 -- Google sub ID
    avatar_url TEXT,
    class      VARCHAR(50)  NOT NULL DEFAULT 'SSC',
    curriculum VARCHAR(50)  NOT NULL DEFAULT 'NCTB',
    tier       VARCHAR(20)  NOT NULL DEFAULT 'free',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id         SERIAL PRIMARY KEY,
    email      VARCHAR(255) NOT NULL,
    code       VARCHAR(6)   NOT NULL,
    purpose    VARCHAR(30)  NOT NULL DEFAULT 'reset',  -- 'reset' | 'verify'
    expires_at TIMESTAMPTZ  NOT NULL,
    used       BOOLEAN      NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS otp_email_idx ON otp_codes (email, used);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id         SERIAL PRIMARY KEY,
    uid        INTEGER      NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    title      VARCHAR(255),
    subject    VARCHAR(100),
    curriculum VARCHAR(50),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         SERIAL PRIMARY KEY,
    session_id INTEGER      NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role       VARCHAR(20)  NOT NULL,   -- 'user' | 'assistant'
    content    TEXT         NOT NULL,
    sources    JSONB,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages (session_id);
