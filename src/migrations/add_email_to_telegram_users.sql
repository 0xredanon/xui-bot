-- Add email column to telegram_users table
ALTER TABLE telegram_users ADD COLUMN IF NOT EXISTS email VARCHAR(255) NULL; 