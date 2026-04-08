-- =============================================================================
-- PaymentDB — Payment Service
-- MySQL 8.0
-- Includes: payment_record table
-- Sample dataset: minimal with sample transactions
-- =============================================================================

CREATE DATABASE IF NOT EXISTS payment_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE payment_db;

-- Drop existing tables
DROP TABLE IF EXISTS payment_record;

-- Table: payment_record
CREATE TABLE payment_record (
  paymentId               VARCHAR(36)    NOT NULL,
  userId                  VARCHAR(36)    NOT NULL,
  ticketId                VARCHAR(36)    NOT NULL,
  concertId               VARCHAR(36)    NOT NULL,
  type                    VARCHAR(20)    NOT NULL  COMMENT 'PURCHASE or REFUND',
  amount                  DECIMAL(10,2)  NOT NULL,
  currency                VARCHAR(3)     NOT NULL  DEFAULT 'SGD',
  status                  VARCHAR(20)    NOT NULL  DEFAULT 'PENDING',
  stripePaymentIntentId   VARCHAR(100)   NULL,
  stripeRefundId          VARCHAR(100)   NULL,
  originalPaymentId       VARCHAR(36)    NULL      COMMENT 'For refunds, links to original payment',
  reason                  VARCHAR(200)   NULL,
  createdAt               DATETIME       NOT NULL  DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (paymentId),
  KEY idx_payment_concert_type (concertId, type),
  KEY idx_payment_user (userId),
  KEY idx_payment_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- No sample payments are seeded by default.
-- Payment records are expected to be created by purchase, resale, and refund flows.
