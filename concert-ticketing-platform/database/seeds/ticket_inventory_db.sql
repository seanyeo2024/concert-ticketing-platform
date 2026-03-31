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

-- =============================================================================
-- SAMPLE DATA  (30 tickets)
-- =============================================================================
-- Status spread to support demo of all 3 scenarios:
--
--   AVAILABLE      — can be picked up by a queue-window user (S1)
--   PENDING        — someone is mid-purchase right now (S1 in-flight)
--   CONFIRMED      — owned; some of these can be listed for resale (S2)
--   RESALE_LISTED  — seller has listed; buyer can browse (S2a done)
--   RESALE_PENDING — buyer is mid-purchase of resale ticket (S2b in-flight)
--   USED           — scanned at gate; past event (Bruno Mars)
--   REFUNDED       — concert cancelled; refund issued (BTS, S3)
--
-- Seat numbering convention:
--   Floor/Pit   → F-RR-CC  (e.g. F-01-01)
--   Lower Tier  → L-RR-CC
--   Upper Tier  → U-RR-CC
--   Gallery     → G-RR-CC
-- =============================================================================

INSERT INTO ticket
  (ticketId, concertId, seatNumber, categoryId,
   ownerId, status, purchasePrice, resalePrice, resaleListingId,
   version, createdAt, updatedAt)
VALUES

-- ============================================================================
-- CONC-000001  Taylor Swift — 12 tickets
-- Covers: AVAILABLE, PENDING, CONFIRMED, RESALE_LISTED, RESALE_PENDING
-- ============================================================================

-- ── CAT 1 Floor / Pit  (basePrice 388.00) ────────────────────────────────────
(
  'TKT-10001', 'CONC-000001', 'F-01-01', 'CAT-C001-01',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-01-10 09:00:00', '2025-01-10 09:00:00'
),
(
  'TKT-10002', 'CONC-000001', 'F-01-02', 'CAT-C001-01',
  'USR-0042', 'PENDING', NULL, NULL, NULL,
  1, '2025-01-10 09:00:00', '2025-06-14 09:18:00'
  -- Mid-purchase: queue window granted, payment not yet confirmed
),
(
  'TKT-10003', 'CONC-000001', 'F-01-03', 'CAT-C001-01',
  'USR-0099', 'CONFIRMED', 388.00, NULL, NULL,
  2, '2025-01-10 09:00:00', '2025-05-20 14:30:00'
),
(
  'TKT-10004', 'CONC-000001', 'F-01-04', 'CAT-C001-01',
  'USR-0115', 'CONFIRMED', 388.00, NULL, NULL,
  2, '2025-01-10 09:00:00', '2025-05-21 10:00:00'
),

-- ── CAT 2 Lower Tier  (basePrice 248.00) ─────────────────────────────────────
(
  'TKT-10005', 'CONC-000001', 'L-03-08', 'CAT-C001-02',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-01-10 09:00:00', '2025-01-10 09:00:00'
),
(
  'TKT-10006', 'CONC-000001', 'L-03-09', 'CAT-C001-02',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-01-10 09:00:00', '2025-01-10 09:00:00'
),
(
  'TKT-10007', 'CONC-000001', 'L-05-12', 'CAT-C001-02',
  'USR-0201', 'CONFIRMED', 248.00, NULL, NULL,
  3, '2025-01-10 09:00:00', '2025-04-15 16:45:00'
),

-- ── CAT 2 — RESALE_LISTED: USR-0201 lists TKT-10007 for resale ───────────────
-- (re-insert with updated values to reflect S2a having run)
-- NOTE: updating TKT-10007 inline for clarity
-- Actual RESALE_LISTED ticket:
(
  'TKT-10008', 'CONC-000001', 'L-05-13', 'CAT-C001-02',
  'USR-0303', 'RESALE_LISTED', 248.00, 320.00, 'LST-10008-001',
  4, '2025-01-10 09:00:00', '2025-07-01 11:00:00'
  -- Seller USR-0303 listed at 320.00 (below 370.00 ceiling)
),

-- ── CAT 2 — RESALE_PENDING: buyer mid-purchase ────────────────────────────────
(
  'TKT-10009', 'CONC-000001', 'L-06-01', 'CAT-C001-02',
  'USR-0410', 'RESALE_PENDING', 248.00, 310.00, 'LST-10009-001',
  5, '2025-01-10 09:00:00', '2025-07-10 14:22:00'
  -- Buyer USR-0512 about to complete purchase; ownerId still seller USR-0410
),

-- ── CAT 3 Upper Tier  (basePrice 158.00) ─────────────────────────────────────
(
  'TKT-10010', 'CONC-000001', 'U-10-05', 'CAT-C001-03',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-01-10 09:00:00', '2025-01-10 09:00:00'
),
(
  'TKT-10011', 'CONC-000001', 'U-10-06', 'CAT-C001-03',
  'USR-0601', 'CONFIRMED', 158.00, NULL, NULL,
  2, '2025-01-10 09:00:00', '2025-06-01 08:00:00'
),

-- ── CAT 4 Gallery  (basePrice 98.00) ─────────────────────────────────────────
(
  'TKT-10012', 'CONC-000001', 'G-01-22', 'CAT-C001-04',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-01-10 09:00:00', '2025-01-10 09:00:00'
),

-- ============================================================================
-- CONC-000002  Coldplay — 10 tickets
-- Mostly AVAILABLE and CONFIRMED; one PENDING to show active queue window
-- ============================================================================

-- ── CAT 1 Floor / Pit  (basePrice 298.00) ────────────────────────────────────
(
  'TKT-20001', 'CONC-000002', 'F-01-01', 'CAT-C002-01',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-02-14 10:00:00', '2025-02-14 10:00:00'
),
(
  'TKT-20002', 'CONC-000002', 'F-01-02', 'CAT-C002-01',
  'USR-0701', 'CONFIRMED', 298.00, NULL, NULL,
  2, '2025-02-14 10:00:00', '2025-07-05 12:30:00'
),
(
  'TKT-20003', 'CONC-000002', 'F-01-03', 'CAT-C002-01',
  'USR-0802', 'PENDING', NULL, NULL, NULL,
  1, '2025-02-14 10:00:00', '2025-07-15 09:55:00'
  -- Active queue window; payment in progress
),

-- ── CAT 2 Lower Tier  (basePrice 188.00) ─────────────────────────────────────
(
  'TKT-20004', 'CONC-000002', 'L-02-04', 'CAT-C002-02',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-02-14 10:00:00', '2025-02-14 10:00:00'
),
(
  'TKT-20005', 'CONC-000002', 'L-02-05', 'CAT-C002-02',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-02-14 10:00:00', '2025-02-14 10:00:00'
),
(
  'TKT-20006', 'CONC-000002', 'L-04-11', 'CAT-C002-02',
  'USR-0901', 'CONFIRMED', 188.00, NULL, NULL,
  2, '2025-02-14 10:00:00', '2025-06-20 15:10:00'
),

-- ── CAT 3 Upper Tier  (basePrice 118.00) ─────────────────────────────────────
(
  'TKT-20007', 'CONC-000002', 'U-08-03', 'CAT-C002-03',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-02-14 10:00:00', '2025-02-14 10:00:00'
),
(
  'TKT-20008', 'CONC-000002', 'U-08-04', 'CAT-C002-03',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-02-14 10:00:00', '2025-02-14 10:00:00'
),

-- ── CAT 4 Gallery  (basePrice 68.00) ─────────────────────────────────────────
(
  'TKT-20009', 'CONC-000002', 'G-02-10', 'CAT-C002-04',
  NULL, 'AVAILABLE', NULL, NULL, NULL,
  0, '2025-02-14 10:00:00', '2025-02-14 10:00:00'
),
(
  'TKT-20010', 'CONC-000002', 'G-02-11', 'CAT-C002-04',
  'USR-1001', 'CONFIRMED', 68.00, NULL, NULL,
  2, '2025-02-14 10:00:00', '2025-07-01 10:00:00'
),

-- ============================================================================
-- CONC-000003  Bruno Mars — 5 tickets  (all USED; sold-out past event)
-- ============================================================================
(
  'TKT-30001', 'CONC-000003', 'F-01-01', 'CAT-C003-01',
  'USR-1101', 'USED', 488.00, NULL, NULL,
  3, '2025-03-01 11:00:00', '2025-08-03 22:05:00'
),
(
  'TKT-30002', 'CONC-000003', 'L-01-05', 'CAT-C003-02',
  'USR-1202', 'USED', 288.00, NULL, NULL,
  3, '2025-03-01 11:00:00', '2025-08-03 22:06:00'
),
(
  'TKT-30003', 'CONC-000003', 'L-02-08', 'CAT-C003-02',
  'USR-1303', 'USED', 288.00, NULL, NULL,
  3, '2025-03-01 11:00:00', '2025-08-03 22:06:00'
),
(
  'TKT-30004', 'CONC-000003', 'U-05-03', 'CAT-C003-03',
  'USR-1404', 'USED', 168.00, NULL, NULL,
  3, '2025-03-01 11:00:00', '2025-08-03 22:07:00'
),
(
  'TKT-30005', 'CONC-000003', 'G-01-14', 'CAT-C003-04',
  'USR-1505', 'USED', 98.00, NULL, NULL,
  3, '2025-03-01 11:00:00', '2025-08-03 22:08:00'
),

-- ============================================================================
-- CONC-000004  BTS Cancelled — 3 tickets  (all REFUNDED; S3 scenario)
-- ============================================================================
(
  'TKT-40001', 'CONC-000004', 'F-02-01', 'CAT-C004-01',
  'USR-1601', 'REFUNDED', 398.00, NULL, NULL,
  4, '2025-01-20 08:00:00', '2025-05-30 14:30:00'
),
(
  'TKT-40002', 'CONC-000004', 'L-03-07', 'CAT-C004-02',
  'USR-1702', 'REFUNDED', 228.00, NULL, NULL,
  4, '2025-01-20 08:00:00', '2025-05-30 14:31:00'
),
(
  'TKT-40003', 'CONC-000004', 'U-07-12', 'CAT-C004-03',
  'USR-1803', 'REFUNDED', 148.00, NULL, NULL,
  4, '2025-01-20 08:00:00', '2025-05-30 14:32:00'
);

-- =============================================================================
-- Quick verification queries (uncomment to run manually)
-- =============================================================================
-- SELECT status, COUNT(*) AS cnt FROM ticket GROUP BY status ORDER BY cnt DESC;
-- SELECT t.ticketId, t.seatNumber, t.status, t.ownerId, t.purchasePrice, t.resalePrice
--   FROM ticket t WHERE t.concertId = 'CONC-000001' ORDER BY t.categoryId, t.seatNumber;
