-- =============================================================================
-- TicketInventoryDB — Ticket Inventory Service
-- MySQL 8.0
-- Includes: ticket table
-- Sample dataset: 30 tickets spread across concerts and scenarios
--   · CONC-000001 (Taylor Swift)   — 12 tickets, mixed statuses (covers S1, S2, S3)
--   · CONC-000002 (Coldplay)       — 10 tickets, mostly AVAILABLE + a few CONFIRMED
--   · CONC-000003 (Bruno Mars)     — 5 tickets, all USED (sold-out, past event feel)
--   · CONC-000004 (BTS Cancelled)  — 3 tickets, all REFUNDED (S3 scenario)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS ticket_inventory_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ticket_inventory_db;

-- -----------------------------------------------------------------------------
-- Table: ticket
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS ticket;

CREATE TABLE ticket (
  ticketId         VARCHAR(36)    NOT NULL,
  concertId        VARCHAR(36)    NOT NULL  COMMENT 'Soft ref → Concert Service concert.concertId',
  seatNumber       VARCHAR(20)    NOT NULL,
  categoryId       VARCHAR(36)    NOT NULL  COMMENT 'Soft ref → Concert Service seat_category.categoryId',
  ownerId          VARCHAR(36)    NULL      DEFAULT NULL COMMENT 'NULL when AVAILABLE',
  status           VARCHAR(20)    NOT NULL  DEFAULT 'AVAILABLE',
  purchasePrice    DECIMAL(10,2)  NULL      DEFAULT NULL COMMENT 'Face-value paid; set on CONFIRMED, never changes',
  resalePrice      DECIMAL(10,2)  NULL      DEFAULT NULL COMMENT 'Asking price set by seller; NULL when not listed',
  resaleListingId  VARCHAR(36)    NULL      DEFAULT NULL COMMENT 'Soft ref to active listing; cleared after sale/cancel',
  version          BIGINT         NOT NULL  DEFAULT 0    COMMENT 'Optimistic lock counter; increment on every UPDATE',
  createdAt        DATETIME       NOT NULL  DEFAULT NOW(),
  updatedAt        DATETIME       NOT NULL  DEFAULT NOW() ON UPDATE NOW(),

  PRIMARY KEY (ticketId),
  UNIQUE KEY uq_concert_seat (concertId, seatNumber),

  CONSTRAINT chk_ticket_status CHECK (
    status IN (
      'AVAILABLE','PENDING','CONFIRMED',
      'RESALE_LISTED','RESALE_PENDING',
      'USED','REFUNDED'
    )
  ),
  -- ownerId must be set when ticket is not available/pending
  CONSTRAINT chk_owner_set CHECK (
    status = 'AVAILABLE'
    OR status = 'PENDING'
    OR ownerId IS NOT NULL
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Composite index: most common query patterns
CREATE INDEX idx_concert_status   ON ticket (concertId, status);
CREATE INDEX idx_owner_status     ON ticket (ownerId,   status);
CREATE INDEX idx_resale_available ON ticket (concertId, status, resalePrice)
  COMMENT 'S2b: browse resale listings for a concert';

-- Seed seats for the current UI category IDs used by CONC-000001.
INSERT INTO ticket (ticketId, concertId, seatNumber, categoryId, status, ownerId, version)
VALUES
  ('TKT-SEED-0001', 'CONC-000001', 'A-01-01', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0002', 'CONC-000001', 'A-01-02', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0003', 'CONC-000001', 'A-01-03', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0004', 'CONC-000001', 'A-01-04', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0005', 'CONC-000001', 'A-01-05', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0006', 'CONC-000001', 'A-01-06', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0007', 'CONC-000001', 'A-01-07', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0008', 'CONC-000001', 'A-01-08', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0009', 'CONC-000001', 'A-01-09', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0010', 'CONC-000001', 'A-01-10', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0011', 'CONC-000001', 'A-01-11', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0012', 'CONC-000001', 'A-01-12', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0013', 'CONC-000001', 'A-01-13', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0014', 'CONC-000001', 'A-01-14', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0015', 'CONC-000001', 'A-01-15', 'CAT-000001-01', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0016', 'CONC-000001', 'B-01-01', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0017', 'CONC-000001', 'B-01-02', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0018', 'CONC-000001', 'B-01-03', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0019', 'CONC-000001', 'B-01-04', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0020', 'CONC-000001', 'B-01-05', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0021', 'CONC-000001', 'B-01-06', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0022', 'CONC-000001', 'B-01-07', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0023', 'CONC-000001', 'B-01-08', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0024', 'CONC-000001', 'B-01-09', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0025', 'CONC-000001', 'B-01-10', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0026', 'CONC-000001', 'B-01-11', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0027', 'CONC-000001', 'B-01-12', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0028', 'CONC-000001', 'B-01-13', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0029', 'CONC-000001', 'B-01-14', 'CAT-000001-02', 'AVAILABLE', NULL, 0),
  ('TKT-SEED-0030', 'CONC-000001', 'B-01-15', 'CAT-000001-02', 'AVAILABLE', NULL, 0)
ON DUPLICATE KEY UPDATE
  concertId = VALUES(concertId),
  seatNumber = VALUES(seatNumber),
  categoryId = VALUES(categoryId),
  status = VALUES(status),
  ownerId = VALUES(ownerId),
  version = VALUES(version),
  updatedAt = CURRENT_TIMESTAMP;

-- No sample tickets are seeded by default.
-- Ticket inventory is expected to be created through the admin Configure Concert flow.
