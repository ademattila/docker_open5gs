USE ims_hss_db;

-- Watchlist (sadece bu!)
CREATE TABLE IF NOT EXISTS li_watchlist (
    id INT PRIMARY KEY AUTO_INCREMENT,
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    imsi VARCHAR(20),
    notes VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Test targets
INSERT INTO li_watchlist (phone_number, imsi, notes, active) VALUES
('+905551234567', '001010000000001', 'Test target 1', TRUE),
('001010000000001', '001010000000001', 'Test target IMSI', TRUE);
