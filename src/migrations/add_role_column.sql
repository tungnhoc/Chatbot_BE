-- Migration: Add Role column to Users table
-- Run this against your Railway MySQL database if the table was created
-- from an older version of mysql.sql that did not include the Role column.
--
-- Usage:
--   mysql -h <host> -P <port> -u <user> -p <database> < src/migrations/add_role_column.sql
--
-- The IF NOT EXISTS guard makes the script safe to re-run.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS Role VARCHAR(20) DEFAULT 'user' NOT NULL;
