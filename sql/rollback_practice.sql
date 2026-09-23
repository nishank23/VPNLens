CREATE TABLE rollback_practice (
    id INTEGER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO rollback_practice (id) VALUES (1);
SELECT * FROM rollback_practice;

	BEGIN;
    TRUNCATE TABLE rollback_practice;
    INSERT INTO rollback_practice (id) VALUES (2);
    INSERT INTO rollback_practice (id) VALUES (2);
    ROLLBACK;
SELECT * FROM rollback_practice;
SELECT COUNT(*) FROM raw_ip2location;

