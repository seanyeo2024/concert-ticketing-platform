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

-- Sample seed data
INSERT INTO qr_record
  (qrId, ticketId, concertId, userId, qrData, qrImageUrl, isValid, generatedAt)
VALUES
  ('QR-10001', 'TKT-10003', 'CONC-000001', 'USR-0042', 'Solstitix|TKT-10003|USR-0042|CONC-000001|demo1234', 'data:image/png;base64,iVBORw0KGgoAAAANS==', 1, '2025-05-20 14:30:00'),
  ('QR-10002', 'TKT-30001', 'CONC-000003', 'USR-0042', 'Solstitix|TKT-30001|USR-0042|CONC-000003|demo5678', 'data:image/png;base64,iVBORw0KGgoAAAANS==', 0, '2025-03-01 11:00:00');
