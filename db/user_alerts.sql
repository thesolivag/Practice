-- Manual watches are shared tables with explicit user_id ownership, never rewritten by tenancy.
CREATE TABLE IF NOT EXISTS manual_alert_users (
 user_id BIGINT PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS manual_alerts (
 id BIGINT AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 pair VARCHAR(12) NOT NULL,
 `condition` VARCHAR(24) NOT NULL,
 timeframe VARCHAR(4) NOT NULL,
 side VARCHAR(8) NOT NULL,
 level DOUBLE NOT NULL,
 engulfing TINYINT(1) NOT NULL DEFAULT 0,
 note VARCHAR(300) NOT NULL DEFAULT '',
 options_json TEXT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
 created_at BIGINT NOT NULL,
 expires_at BIGINT NOT NULL,
 last_checked BIGINT NOT NULL,
 last_attempt BIGINT NOT NULL DEFAULT 0,
 last_quote DOUBLE NULL,
 quote_time BIGINT NULL,
 event_time BIGINT NULL,
 event_payload TEXT NULL,
 lease_token CHAR(32) NULL,
 lease_until BIGINT NOT NULL DEFAULT 0,
 sent_at BIGINT NULL,
 error VARCHAR(160) NULL,
 KEY ix_manual_user (user_id,created_at),
 KEY ix_manual_due (status,last_attempt),
 KEY ix_manual_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Successfully delivered immutable event anchors, bounded by count and age at ACK.
CREATE TABLE IF NOT EXISTS manual_alert_events (
 id BIGINT AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 watch_id BIGINT NOT NULL,
 pair VARCHAR(12) NOT NULL,
 event_time BIGINT NOT NULL,
 model VARCHAR(24) NOT NULL,
 timeframe VARCHAR(8) NOT NULL,
 side VARCHAR(8) NOT NULL,
 level DOUBLE NULL,
 event_payload TEXT NOT NULL,
 sent_at BIGINT NOT NULL,
 UNIQUE KEY uq_manual_event (user_id,watch_id,event_time,model,timeframe,side),
 KEY ix_manual_event_user (user_id,id),
 KEY ix_manual_event_age (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
