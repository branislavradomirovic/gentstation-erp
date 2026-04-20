-- GentStationAI PostgreSQL Initialization Script
-- This script runs when the PostgreSQL container starts
-- It creates the database and user if they don't exist

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Note: Database and user are created by docker-compose POSTGRES_* variables
-- This script just ensures extensions are available

-- Create schema comment
COMMENT ON DATABASE gentstation IS 'GentStationAI - Gas Station Management System';
