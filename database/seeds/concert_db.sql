-- =============================================================================
-- ConcertDB — Concert Service
-- MySQL 8.0
-- Includes: concert, seat_category tables
-- Sample dataset: 5 concerts × varied seat categories
-- =============================================================================

CREATE DATABASE IF NOT EXISTS concert_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE concert_db;

-- -----------------------------------------------------------------------------
-- Table: concert
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS seat_category;
DROP TABLE IF EXISTS concert;

CREATE TABLE concert (
  concertId          VARCHAR(36)   NOT NULL,
  name               VARCHAR(200)  NOT NULL,
  artistName         VARCHAR(100)  NOT NULL,
  venue              VARCHAR(200)  NOT NULL,
  eventDate          DATETIME      NOT NULL COMMENT 'Stored as UTC',
  totalSeats         INT           NOT NULL DEFAULT 0 CHECK (totalSeats >= 0),
  availableSeats     INT           NOT NULL DEFAULT 0 CHECK (availableSeats >= 0),
  status             VARCHAR(20)   NOT NULL DEFAULT 'ACTIVE',
  cancellationReason VARCHAR(500)  NULL     DEFAULT NULL,
  currency           VARCHAR(3)    NOT NULL DEFAULT 'SGD',
  createdAt          DATETIME      NOT NULL DEFAULT NOW(),
  updatedAt          DATETIME      NOT NULL DEFAULT NOW() ON UPDATE NOW(),

  PRIMARY KEY (concertId),
  CONSTRAINT chk_concert_status
    CHECK (status IN ('ACTIVE','SOLD_OUT','CANCELLED','POSTPONED')),
  CONSTRAINT chk_available_lte_total
    CHECK (availableSeats <= totalSeats)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- Table: seat_category
-- -----------------------------------------------------------------------------
CREATE TABLE seat_category (
  categoryId      VARCHAR(36)   NOT NULL,
  concertId       VARCHAR(36)   NOT NULL,
  categoryName    VARCHAR(100)  NOT NULL,
  totalSeats      INT           NOT NULL DEFAULT 0 CHECK (totalSeats >= 0),
  availableSeats  INT           NOT NULL DEFAULT 0 CHECK (availableSeats >= 0),
  createdAt       DATETIME      NOT NULL DEFAULT NOW(),

  PRIMARY KEY (categoryId),
  CONSTRAINT fk_seatcat_concert
    FOREIGN KEY (concertId) REFERENCES concert (concertId)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT chk_seatcat_available
    CHECK (availableSeats <= totalSeats)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================================================
-- SAMPLE DATA
-- =============================================================================
-- 5 concerts
--   CONC-000001  Taylor Swift — The Eras Tour          (ACTIVE,    SGD)
--   CONC-000002  Coldplay — Music of the Spheres        (ACTIVE,    SGD)
--   CONC-000003  Bruno Mars — 24K Magic Live            (SOLD_OUT,  SGD)
--   CONC-000004  BTS — Yet To Come                      (CANCELLED, SGD)
--   CONC-000005  Ed Sheeran — Mathematics Tour          (POSTPONED, SGD)
-- Each concert has 4 seat categories (CAT1–CAT4)
-- Total rows: 5 concerts + 20 seat_category rows
-- =============================================================================

-- -----------------------------------------------------------------------------
-- concert rows
-- -----------------------------------------------------------------------------
INSERT INTO concert
  (concertId, name, artistName, venue, eventDate,
   totalSeats, availableSeats, status, cancellationReason, currency,
   createdAt, updatedAt)
VALUES
-- CONC-000001 · Taylor Swift · ACTIVE
(
  'CONC-000001',
  'Taylor Swift — The Eras Tour',
  'Taylor Swift',
  'National Stadium, Singapore',
  '2025-09-14 19:00:00',
  50000, 18430, 'ACTIVE', NULL, 'SGD',
  '2025-01-10 08:00:00', '2025-06-01 12:00:00'
),
-- CONC-000002 · Coldplay · ACTIVE
(
  'CONC-000002',
  'Coldplay — Music of the Spheres World Tour',
  'Coldplay',
  'Singapore Indoor Stadium',
  '2025-11-22 20:00:00',
  12000, 4210, 'ACTIVE', NULL, 'SGD',
  '2025-02-14 09:30:00', '2025-07-15 11:00:00'
),
-- CONC-000003 · Bruno Mars · SOLD_OUT
(
  'CONC-000003',
  'Bruno Mars — 24K Magic Live in Singapore',
  'Bruno Mars',
  'Resorts World Theatre, Singapore',
  '2025-08-03 21:00:00',
  5000, 0, 'SOLD_OUT', NULL, 'SGD',
  '2025-03-01 10:00:00', '2025-07-20 09:45:00'
),
-- CONC-000004 · BTS · CANCELLED
(
  'CONC-000004',
  'BTS — Yet To Come in Singapore',
  'BTS',
  'Singapore Sports Hub, Kallang',
  '2025-07-05 18:00:00',
  55000, 55000, 'CANCELLED',
  'Tour postponed due to mandatory military service of members.',
  'SGD',
  '2025-01-20 07:00:00', '2025-05-30 14:00:00'
),
-- CONC-000005 · Ed Sheeran · POSTPONED
(
  'CONC-000005',
  'Ed Sheeran — Mathematics Tour',
  'Ed Sheeran',
  'Changi Exhibition Centre, Singapore',
  '2025-10-18 19:30:00',
  30000, 22100, 'POSTPONED', NULL, 'SGD',
  '2025-04-05 11:00:00', '2025-08-01 16:30:00'
);

-- -----------------------------------------------------------------------------
-- seat_category rows  (4 categories per concert = 20 rows)
-- Naming convention: CAT1=Floor/Pit, CAT2=Lower, CAT3=Upper, CAT4=Gallery
-- -----------------------------------------------------------------------------
INSERT INTO seat_category
  (categoryId, concertId, categoryName, totalSeats, availableSeats, createdAt)
VALUES
-- ── CONC-000001  Taylor Swift ────────────────────────────────────────────────
('CAT-C001-01', 'CONC-000001', 'CAT 1 — Floor / Pit',        5000,  230,  '2025-01-10 08:05:00'),
('CAT-C001-02', 'CONC-000001', 'CAT 2 — Lower Tier',        15000, 4100,  '2025-01-10 08:05:00'),
('CAT-C001-03', 'CONC-000001', 'CAT 3 — Upper Tier',        20000, 8100,  '2025-01-10 08:05:00'),
('CAT-C001-04', 'CONC-000001', 'CAT 4 — Gallery',           10000, 6000,  '2025-01-10 08:05:00'),

-- ── CONC-000002  Coldplay ────────────────────────────────────────────────────
('CAT-C002-01', 'CONC-000002', 'CAT 1 — Floor / Pit',        1500,   80,  '2025-02-14 09:35:00'),
('CAT-C002-02', 'CONC-000002', 'CAT 2 — Lower Tier',         4500,  930,  '2025-02-14 09:35:00'),
('CAT-C002-03', 'CONC-000002', 'CAT 3 — Upper Tier',         4000, 2200,  '2025-02-14 09:35:00'),
('CAT-C002-04', 'CONC-000002', 'CAT 4 — Gallery',            2000, 1000,  '2025-02-14 09:35:00'),

-- ── CONC-000003  Bruno Mars (SOLD_OUT — all categories at 0) ─────────────────
('CAT-C003-01', 'CONC-000003', 'CAT 1 — Floor / Pit',         500,    0,  '2025-03-01 10:05:00'),
('CAT-C003-02', 'CONC-000003', 'CAT 2 — Lower Tier',         1800,    0,  '2025-03-01 10:05:00'),
('CAT-C003-03', 'CONC-000003', 'CAT 3 — Upper Tier',         1800,    0,  '2025-03-01 10:05:00'),
('CAT-C003-04', 'CONC-000003', 'CAT 4 — Gallery',             900,    0,  '2025-03-01 10:05:00'),

-- ── CONC-000004  BTS (CANCELLED — availableSeats kept as original allocation) 
('CAT-C004-01', 'CONC-000004', 'CAT 1 — Floor / Pit',        8000, 8000,  '2025-01-20 07:05:00'),
('CAT-C004-02', 'CONC-000004', 'CAT 2 — Lower Tier',        17000,17000,  '2025-01-20 07:05:00'),
('CAT-C004-03', 'CONC-000004', 'CAT 3 — Upper Tier',        20000,20000,  '2025-01-20 07:05:00'),
('CAT-C004-04', 'CONC-000004', 'CAT 4 — Gallery',           10000,10000,  '2025-01-20 07:05:00'),

-- ── CONC-000005  Ed Sheeran (POSTPONED — still selling) ──────────────────────
('CAT-C005-01', 'CONC-000005', 'CAT 1 — Floor / Pit',        3000,  600,  '2025-04-05 11:05:00'),
('CAT-C005-02', 'CONC-000005', 'CAT 2 — Lower Tier',        10000, 4500,  '2025-04-05 11:05:00'),
('CAT-C005-03', 'CONC-000005', 'CAT 3 — Upper Tier',        12000, 9000,  '2025-04-05 11:05:00'),
('CAT-C005-04', 'CONC-000005', 'CAT 4 — Gallery',            8000, 8000,  '2025-04-05 11:05:00');

-- Sync concert.totalSeats / availableSeats from seat_category aggregates
UPDATE concert c
JOIN (
  SELECT concertId,
         SUM(totalSeats)     AS tot,
         SUM(availableSeats) AS avail
  FROM seat_category
  GROUP BY concertId
) s ON c.concertId = s.concertId
SET c.totalSeats     = s.tot,
    c.availableSeats = s.avail;

-- =============================================================================
-- Quick verification queries (commented out — uncomment to run manually)
-- =============================================================================
-- SELECT * FROM concert;
-- SELECT sc.*, c.name AS concertName
--   FROM seat_category sc
--   JOIN concert c USING (concertId)
--   ORDER BY sc.concertId, sc.categoryId;
