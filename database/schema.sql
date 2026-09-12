-- Civic Issue Reporting System - Database Schema (PostgreSQL)
-- Run this in pgAdmin's Query Tool, connected to your target database.

-- 1. Users (citizens + admins)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'citizen' CHECK (role IN ('citizen', 'admin')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Departments (who handles what)
CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL   -- e.g. 'pothole', 'garbage', 'water_leak'
);

INSERT INTO departments (name, category)
SELECT * FROM (VALUES
    ('Roads & Infrastructure Dept', 'pothole'),
    ('Sanitation Dept', 'garbage'),
    ('Water Works Dept', 'water_leak'),
    ('Electrical Dept', 'streetlight')
) AS d(name, category)
WHERE NOT EXISTS (SELECT 1 FROM departments);

-- 3. Complaints
CREATE TABLE IF NOT EXISTS complaints (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    department_id INT REFERENCES departments(id),
    category VARCHAR(50),            -- filled in by the AI detector
    description TEXT,
    image_path VARCHAR(255),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'resolved')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
