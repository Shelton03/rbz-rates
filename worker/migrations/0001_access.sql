-- Accounts, API keys and usage counters for the rbz-rates API (Cloudflare D1 / SQLite).

-- One row per signed-in account (id is the GitHub user id, set by the website).
CREATE TABLE users (
    id          TEXT PRIMARY KEY,
    login       TEXT NOT NULL,
    email       TEXT,
    created_at  TEXT NOT NULL
);

-- Only a SHA-256 hash of each key is stored; the key itself is shown once, at creation.
CREATE TABLE api_keys (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    prefix      TEXT NOT NULL,          -- first characters, so people can tell keys apart
    hash        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    revoked_at  TEXT
);
CREATE INDEX api_keys_user ON api_keys(user_id);

-- Request counts per UTC day, per caller, per endpoint. One upsert per counted request.
-- subject is 'key:<api_keys.id>' or 'anon:<hash of IP + daily salt>' (raw IPs are never stored).
CREATE TABLE usage (
    day         TEXT NOT NULL,
    subject     TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, subject, endpoint)
);
CREATE INDEX usage_subject ON usage(subject, day);
