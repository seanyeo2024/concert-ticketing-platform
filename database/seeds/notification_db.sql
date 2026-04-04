-- =============================================================================
-- NotificationDB — Notification Service
-- MySQL 8.0
-- Includes: notification_log table
-- Sample dataset: minimal with sample notifications
-- =============================================================================

CREATE DATABASE IF NOT EXISTS notification_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE notification_db;

-- Drop existing tables
DROP TABLE IF EXISTS notification_log;

-- Table: notification_log
CREATE TABLE notification_log (
  notificationId    VARCHAR(36)    NOT NULL,
  userId            VARCHAR(36)    NOT NULL,
  eventType         VARCHAR(60)    NOT NULL,
  channel           VARCHAR(10)    NOT NULL,
  subject           VARCHAR(200)   NULL,
  body              TEXT           NOT NULL,
  status            VARCHAR(20)    NOT NULL  DEFAULT 'PENDING',
  refId             VARCHAR(36)    NULL,
  externalMsgId     VARCHAR(200)   NULL,
  retryCount        INT            NOT NULL  DEFAULT 0,
  sentAt            DATETIME       NULL,
  createdAt         DATETIME       NOT NULL  DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (notificationId),
  KEY idx_notification_user_event (userId, eventType),
  KEY idx_notification_status_retry (status, retryCount)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sample seed data
INSERT INTO notification_log
  (notificationId, userId, eventType, channel, subject, body, status, sentAt, createdAt)
VALUES
  ('NOTIF-001', 'USR-0042', 'ticket.purchased', 'EMAIL', 'Your ticket is confirmed!', 'Your Taylor Swift ticket (TKT-10003) is ready for pickup.', 'SENT', '2025-05-20 14:30:00', '2025-05-20 14:30:00'),
  ('NOTIF-003', 'USR-0042', 'concert.cancelled', 'EMAIL', 'Concert Cancelled — Refund Issued', 'BTS concert (CONC-000004) has been cancelled. Your refund has been processed.', 'SENT', '2025-05-30 14:31:00', '2025-05-30 14:30:00');
