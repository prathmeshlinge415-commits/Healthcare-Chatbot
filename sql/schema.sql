-- Healthcare Aide - database schema (MySQL 8 / MariaDB 10.4+)
-- Run:  mysql -u root -p < sql/schema.sql      (or: python init_db.py)
CREATE DATABASE IF NOT EXISTS Healthcare_chat_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE Healthcare_chat_bot;

CREATE TABLE IF NOT EXISTS patient (
    id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(190) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password VARCHAR(255) NOT NULL,
    date_of_birth VARCHAR(10),
    gender VARCHAR(20),
    city VARCHAR(100),
    blood_group VARCHAR(5),
    emergency_contact_name VARCHAR(120),
    emergency_contact_phone VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doctors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80),
    email VARCHAR(190),
    phone VARCHAR(20),
    specialty VARCHAR(60) NOT NULL,
    experience_years INT DEFAULT 0,
    qualifications VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT,
    patient_name VARCHAR(160) NOT NULL,
    patient_email VARCHAR(190) NOT NULL,
    patient_phone VARCHAR(20) NOT NULL,
    doctor_specialty VARCHAR(60) NOT NULL,
    appointment_date VARCHAR(10) NOT NULL,   -- YYYY-MM-DD
    appointment_time VARCHAR(5) NOT NULL,    -- HH:MM (24h)
    reason VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'confirmed',  -- confirmed | cancelled
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80),
    last_name VARCHAR(80),
    email VARCHAR(190),
    phone VARCHAR(20),
    subject VARCHAR(120),
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT,
    category VARCHAR(30) NOT NULL,
    rating INT,
    message TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    title VARCHAR(160) NOT NULL,
    body VARCHAR(400),
    is_read TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    role VARCHAR(10) NOT NULL,        -- user | bot
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
