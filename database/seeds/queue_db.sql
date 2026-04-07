-- =============================================================================
-- QueueDB — Queue Service
-- MySQL 8.0
-- Includes: queue_entry table
-- Sample dataset: minimal "empty" state (services will populate at runtime)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS queue_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE queue_db;

-- Drop existing tables
DROP TABLE IF EXISTS queue_entry;

-- Table: queue_entry
CREATE TABLE queue_entry (
  queueId           VARCHAR(36)   NOT NULL,
  concertId         VARCHAR(36)   NOT NULL,
  userId            VARCHAR(36)   NOT NULL,
  position          INT           NOT NULL,
  status            VARCHAR(20)   NOT NULL DEFAULT 'WAITING',
  windowGrantedAt   DATETIME      NULL,
  windowExpiresAt   DATETIME      NULL,
  joinedAt          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updatedAt         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (queueId),
  UNIQUE KEY uq_queue_user (concertId, userId),
  KEY idx_concert_status_position (concertId, status, position)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sample data: empty (queue is dynamic)
