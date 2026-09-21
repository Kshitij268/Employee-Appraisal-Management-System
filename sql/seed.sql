

-- Seed Data for Development / Testing

-- HOW TO USE:
--   1. Run schema.sql first to create the database and tables
--   2. Run this file to insert mock data:
--        mysql -u root -p employee_appraisal < sql/seed.sql
--      OR paste into MySQL Workbench and execute

-- DEFAULT LOGIN PASSWORD for ALL demo accounts: Password@123


USE employee_appraisal;

-- ============================================================
-- 1. SEED USERS
-- ============================================================
-- Password placeholder: the Flask app will auto-fix hashes on first run
INSERT INTO users (user_id, name, email, password_hash, role) VALUES
(1, 'Sarah Jenkins',  'hr@example.com',             'PLACEHOLDER_HASH', 'hr'),
(2, 'Alex Rivera',    'manager@example.com',         'PLACEHOLDER_HASH', 'manager'),
(3, 'David Chen',     'employee@example.com',        'PLACEHOLDER_HASH', 'employee'),
(4, 'Emily Watson',   'emily.watson@example.com',    'PLACEHOLDER_HASH', 'employee'),
(5, 'Michael Brown',  'michael.brown@example.com',   'PLACEHOLDER_HASH', 'employee')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- ============================================================
-- 2. SEED EMPLOYEES
-- ============================================================
INSERT INTO employees (employee_id, user_id, employee_code, age, address, department, designation, phone, location, joining_date, manager_id) VALUES
(1, 1, 'EMP-HR-001',  38, '100 Broadway, New York, NY',     'Human Resources', 'HR Director',               '+1 (555) 010-001', 'Headquarters - New York', '2021-03-15', NULL),
(2, 2, 'EMP-ENG-002', 42, '456 Market St, San Jose, CA',     'Engineering',     'Engineering Manager',        '+1 (555) 010-002', 'Headquarters - New York', '2021-06-01', NULL),
(3, 3, 'EMP-ENG-003', 29, '789 Mission St, San Francisco, CA', 'Engineering',     'Senior Full Stack Engineer', '+1 (555) 010-003', 'San Francisco Branch',    '2022-01-10', 2),
(4, 4, 'EMP-ENG-004', 27, '321 Congress Ave, Austin, TX',     'Engineering',     'Frontend UI/UX Engineer',    '+1 (555) 010-004', 'Austin Branch',           '2022-04-18', 2),
(5, 5, 'EMP-ENG-005', 31, '654 Michigan Ave, Chicago, IL',    'Engineering',     'Backend Database Engineer',  '+1 (555) 010-005', 'Remote - Chicago',        '2023-02-01', 2)
ON DUPLICATE KEY UPDATE designation=VALUES(designation);

-- ============================================================
-- 3. SEED PROJECTS
-- ============================================================
INSERT INTO projects (project_id, employee_id, name, category, description, progress, status, priority, due_date, milestones_completed, milestones_total) VALUES
(1, 3, 'NextGen Enterprise Appraisal Portal',  'Platform Engineering', 'End-to-end multi-role appraisal system with automated reviews and audit trails.',      80,  'in_progress', 'High',     '2026-12-15', 4, 5),
(2, 3, 'Zero-Downtime Microservice Migration', 'Infrastructure',       'Migrate legacy monolith services to isolated stateless backend services.',              100, 'completed',   'Critical', '2026-07-20', 6, 6),
(3, 4, 'Unified Corporate Design System',      'UI/UX Design',         'Modern accessible responsive component kit for all internal web tools.',               75,  'in_progress', 'High',     '2026-10-30', 3, 4),
(4, 5, 'High-Availability Database Cluster',   'Infrastructure',       'Configure primary-replica replication with automated failover and backups.',           60,  'in_progress', 'High',     '2026-11-20', 3, 5)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- ============================================================
-- 4. SEED APPRAISALS
-- ============================================================
INSERT INTO appraisals (appraisal_id, employee_id, manager_id, appraisal_period, overall_rating, self_rating, employee_comments, manager_comments, status) VALUES
(1, 3, 2, 'FY2025-Q4', 4.50, 4.70, 'Exceeded delivery targets on architecture modernization and security audits.', 'Outstanding technical leadership and high reliability across projects.', 'APPROVED'),
(2, 3, 2, 'FY2026-Q1', NULL, 4.60, 'Completed core delivery milestones early. Mentored junior developers.',        NULL,                                                                       'UNDER_REVIEW'),
(3, 4, 2, 'FY2026-Q1', 4.20, 4.30, 'Standardized design tokens and eliminated frontend layout drift.',             'Consistently high visual quality and team collaboration.',                 'APPROVED'),
(4, 5, 2, 'FY2026-Q1', 3.20, 4.00, 'Maintained 99.9% database uptime during migration window.',                   'Good delivery, but incident post-mortem documentation was delayed.',       'REJECTED')
ON DUPLICATE KEY UPDATE appraisal_period=VALUES(appraisal_period);

-- ============================================================
-- 5. SEED APPEALS (Michael Brown appeals rejected appraisal)
-- ============================================================
INSERT INTO appeals (appeal_id, appraisal_id, employee_id, reason, status, manager_response) VALUES
(1, 4, 5, 'The incident post-mortems were delayed due to urgent unannounced hardware failures beyond team control.', 'pending', NULL)
ON DUPLICATE KEY UPDATE reason=VALUES(reason);

-- ============================================================
-- 6. SEED INVESTIGATIONS
-- ============================================================
INSERT INTO investigations (investigation_id, employee_id, manager_id, higher_authority_id, appraisal_id, appeal_id, issue_type, subject, description, evidence_details, status) VALUES
(1, 3, 2, 1, 1, NULL, 'Policy Clarification', 'Clarification on Remote Equipment Allowance Policy',
 'Requesting guidance regarding multi-monitor home workstation reimbursement.',
 'Attached receipts submitted on corporate expense portal ticket #4092.', 'pending')
ON DUPLICATE KEY UPDATE subject=VALUES(subject);

-- ============================================================
-- 7. SEED DOCUMENTS
-- ============================================================
INSERT INTO documents (document_id, employee_id, document_type, document_name, document_path, status, manager_comments) VALUES
(1, 3, 'Annual Performance Summary', 'Q4_Architecture_Deliverables.pdf',       'uploads/documents/sample_summary.pdf', 'approved', 'Verified and thoroughly documented deliverables.'),
(2, 3, 'Technical Certification',    'AWS_Solutions_Architect_Certificate.pdf', 'uploads/documents/sample_cert.pdf',    'pending',  NULL)
ON DUPLICATE KEY UPDATE document_name=VALUES(document_name);

-- ============================================================
-- 8. SEED DOCUMENT VERIFICATION
-- ============================================================
INSERT INTO document_verification (verification_id, document_id, manager_id, action, comments) VALUES
(1, 1, 2, 'approved', 'All deliverables match repository commit logs and sprint metrics.')
ON DUPLICATE KEY UPDATE comments=VALUES(comments);

-- ============================================================
-- 9. SEED AUDIT LOGS
-- ============================================================
INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description) VALUES
(1, 'SYSTEM_INIT',      'DATABASE',    1, 'Initial database schema and system configuration loaded.'),
(2, 'REVIEW_APPRAISAL', 'APPRAISAL',   1, 'Manager Alex Rivera approved appraisal for David Chen (FY2025-Q4).'),
(3, 'SUBMIT_APPRAISAL', 'APPRAISAL',   2, 'David Chen submitted self-appraisal for FY2026-Q1.'),
(5, 'SUBMIT_APPEAL',    'APPEAL',      1, 'Michael Brown submitted appeal for appraisal #4.');
