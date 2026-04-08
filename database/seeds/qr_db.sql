-- =============================================================================
-- QR_DB — QR Service
-- MySQL 8.0
-- Includes: qr_record table
-- Sample dataset: minimal with sample QR records
-- =============================================================================

CREATE DATABASE IF NOT EXISTS qr_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE qr_db;

-- Drop existing tables
DROP TABLE IF EXISTS qr_record;

-- Table: qr_record
CREATE TABLE qr_record (
  qrId              VARCHAR(36)    NOT NULL,
  ticketId          VARCHAR(36)    NOT NULL,
  concertId         VARCHAR(36)    NOT NULL,
  userId            VARCHAR(36)    NOT NULL,
  qrData            TEXT           NOT NULL,
  qrImageUrl        MEDIUMTEXT     NOT NULL,
  isValid           TINYINT(1)     NOT NULL  DEFAULT 1,
  invalidatedAt     DATETIME       NULL,
  invalidReason     VARCHAR(100)   NULL,
  generatedAt       DATETIME       NOT NULL  DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (qrId),
  KEY idx_qr_ticket_valid (ticketId, isValid),
  KEY idx_qr_concert_valid (concertId, isValid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- No sample QR records are seeded by default.
-- QR records are expected to be generated during purchase and resale flows.
