-- Global auth tables: account identity always originates in verified Telegram initData.
CREATE TABLE IF NOT EXISTS web_auth_codes (
 code_hash CHAR(64) PRIMARY KEY,
 user_id BIGINT NOT NULL,
 client VARCHAR(16) NOT NULL,
 created_at BIGINT NOT NULL,
 expires_at BIGINT NOT NULL,
 used_at BIGINT NULL,
 KEY ix_auth_code_expiry (expires_at),
 KEY ix_auth_code_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS browser_sessions (
 id CHAR(32) PRIMARY KEY,
 token_hash CHAR(64) NOT NULL UNIQUE,
 user_id BIGINT NOT NULL,
 client VARCHAR(16) NOT NULL,
 name VARCHAR(80) NOT NULL,
 created_at BIGINT NOT NULL,
 expires_at BIGINT NOT NULL,
 revoked_at BIGINT NULL,
 KEY ix_browser_user (user_id, expires_at),
 KEY ix_browser_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS auth_rate_limits (
 k CHAR(64) PRIMARY KEY,
 attempts INT NOT NULL,
 expires_at BIGINT NOT NULL,
 KEY ix_auth_rate_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
