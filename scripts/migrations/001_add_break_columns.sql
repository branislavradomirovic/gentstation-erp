-- Migration: add persistent break tracking columns to employee_shifts
-- Idempotent: uses IF NOT EXISTS so it can be applied safely multiple times.

BEGIN;

ALTER TABLE employee_shifts
    ADD COLUMN IF NOT EXISTS break_started_at TIMESTAMP;

ALTER TABLE employee_shifts
    ADD COLUMN IF NOT EXISTS break_ended_at TIMESTAMP;

ALTER TABLE employee_shifts
    ADD COLUMN IF NOT EXISTS break_duration_minutes INTEGER DEFAULT 15;

ALTER TABLE employee_shifts
    ADD COLUMN IF NOT EXISTS is_on_break BOOLEAN DEFAULT FALSE;

-- Ensure existing NULLs have a default where appropriate
UPDATE employee_shifts
SET break_duration_minutes = 15
WHERE break_duration_minutes IS NULL;

COMMIT;
