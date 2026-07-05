-- Qualifay initial DB setup
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
SELECT 'Qualifay DB initialized' AS status;
