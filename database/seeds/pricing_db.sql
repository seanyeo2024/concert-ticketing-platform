CREATE DATABASE IF NOT EXISTS pricing_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE pricing_db;

DROP TABLE IF EXISTS price_rule;

CREATE TABLE price_rule (
  priceRuleId VARCHAR(36) NOT NULL,
  concertId VARCHAR(36) NOT NULL,
  categoryId VARCHAR(36) NOT NULL,
  basePrice DECIMAL(10,2) NOT NULL,
  resaleCeiling DECIMAL(10,2) NULL,
  currency VARCHAR(3) NOT NULL DEFAULT 'SGD',
  effectiveFrom DATETIME NOT NULL,
  effectiveTo DATETIME NULL,
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (priceRuleId),
  UNIQUE KEY uq_price_rule (concertId, categoryId, effectiveFrom)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- No sample pricing rules are seeded by default.
-- Pricing rules are expected to be created through the admin Configure Concert flow.
