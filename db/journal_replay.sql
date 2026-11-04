-- Journal rows are scoped explicitly, including the legacy owner.
CREATE TABLE IF NOT EXISTS trade_journal (
 id BIGINT AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 source_kind VARCHAR(12) NOT NULL,
 source_id BIGINT NULL,
 pair VARCHAR(12) NOT NULL,
 side VARCHAR(4) NOT NULL,
 entry DOUBLE NULL,
 stop DOUBLE NULL,
 target DOUBLE NULL,
 result_r DOUBLE NULL,
 outcome VARCHAR(12) NOT NULL DEFAULT 'OPEN',
 notes TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 KEY ix_journal_user (user_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Global shared, compressed H1 month chunks; never copied per user.
CREATE TABLE IF NOT EXISTS replay_candles (
 pair VARCHAR(12) NOT NULL,
 month CHAR(7) NOT NULL,
 payload MEDIUMBLOB NOT NULL,
 provider VARCHAR(16) NOT NULL,
 bytes INT NOT NULL,
 covered_until BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 PRIMARY KEY(pair,month),
 KEY ix_replay_age(updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS replay_requests (
 id BIGINT AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 pair VARCHAR(12) NOT NULL,
 lo BIGINT NOT NULL,
 hi BIGINT NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'QUEUED',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE KEY uq_replay_request(user_id,pair,lo,hi),
 KEY ix_replay_queue(status,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
