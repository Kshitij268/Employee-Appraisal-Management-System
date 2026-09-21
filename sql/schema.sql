-- Run schema.sql FIRST, then seed.sql.

CREATE DATABASE IF NOT EXISTS employee_appraisal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE employee_appraisal;


-- 1. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'employee',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_email (email),
    INDEX idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. EMPLOYEES TABLE
CREATE TABLE IF NOT EXISTS employees (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    employee_code VARCHAR(50) NOT NULL UNIQUE,
    age INT NULL,
    address TEXT NULL,
    department VARCHAR(100),
    designation VARCHAR(100),
    phone VARCHAR(50),
    location VARCHAR(100),
    joining_date DATE,
    manager_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_employees_user FOREIGN KEY (user_id) 
        REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_employees_manager FOREIGN KEY (manager_id) 
        REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_employees_user (user_id),
    INDEX idx_employees_manager (manager_id),
    INDEX idx_employees_dept (department),
    INDEX idx_employees_code (employee_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. DOCUMENTS TABLE
CREATE TABLE IF NOT EXISTS documents (
    document_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    document_type VARCHAR(100) NOT NULL,
    document_name VARCHAR(255) NOT NULL,
    document_path VARCHAR(500) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    manager_comments TEXT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_documents_employee FOREIGN KEY (employee_id) 
        REFERENCES employees(employee_id) ON DELETE CASCADE,
    INDEX idx_documents_employee (employee_id),
    INDEX idx_documents_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. DOCUMENT VERIFICATION TABLE
CREATE TABLE IF NOT EXISTS document_verification (
    verification_id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    manager_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    comments TEXT NULL,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_doc_verif_doc FOREIGN KEY (document_id) 
        REFERENCES documents(document_id) ON DELETE CASCADE,
    CONSTRAINT fk_doc_verif_manager FOREIGN KEY (manager_id) 
        REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_verif_doc (document_id),
    INDEX idx_verif_manager (manager_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. APPRAISALS TABLE
CREATE TABLE IF NOT EXISTS appraisals (
    appraisal_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    manager_id INT NULL,
    hr_id INT NULL,
    appraisal_period VARCHAR(50) NOT NULL,
    overall_rating DECIMAL(3,2) NULL,
    self_rating DECIMAL(3,2) NULL,
    employee_comments TEXT NULL,
    manager_comments TEXT NULL,
    status VARCHAR(50) DEFAULT 'UNDER_REVIEW',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_appraisals_employee FOREIGN KEY (employee_id) 
        REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_appraisals_manager FOREIGN KEY (manager_id) 
        REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT fk_appraisals_hr FOREIGN KEY (hr_id)
        REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_appraisals_employee (employee_id),
    INDEX idx_appraisals_manager (manager_id),
    INDEX idx_appraisals_hr (hr_id),
    INDEX idx_appraisals_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. APPEALS TABLE
CREATE TABLE IF NOT EXISTS appeals (
    appeal_id INT AUTO_INCREMENT PRIMARY KEY,
    appraisal_id INT NOT NULL,
    employee_id INT NOT NULL,
    manager_id INT NULL,
    hr_id INT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    manager_response TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_appeals_appraisal FOREIGN KEY (appraisal_id) 
        REFERENCES appraisals(appraisal_id) ON DELETE CASCADE,
    CONSTRAINT fk_appeals_employee FOREIGN KEY (employee_id) 
        REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_appeals_manager FOREIGN KEY (manager_id)
        REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT fk_appeals_hr FOREIGN KEY (hr_id)
        REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_appeals_appraisal (appraisal_id),
    INDEX idx_appeals_employee (employee_id),
    INDEX idx_appeals_manager (manager_id),
    INDEX idx_appeals_hr (hr_id),
    INDEX idx_appeals_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. INVESTIGATIONS TABLE (HR Complaints & Escalations)
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    manager_id INT NULL,
    higher_authority_id INT NULL,
    appraisal_id INT NULL,
    appeal_id INT NULL,
    issue_type VARCHAR(100) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    evidence_details TEXT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    authority_response TEXT NULL,
    reviewed_by INT NULL,
    resolved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_investigations_employee FOREIGN KEY (employee_id) 
        REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_investigations_manager FOREIGN KEY (manager_id) 
        REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT fk_investigations_authority FOREIGN KEY (higher_authority_id) 
        REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT fk_investigations_reviewer FOREIGN KEY (reviewed_by) 
        REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT fk_investigations_appraisal FOREIGN KEY (appraisal_id) 
        REFERENCES appraisals(appraisal_id) ON DELETE SET NULL,
    CONSTRAINT fk_investigations_appeal FOREIGN KEY (appeal_id) 
        REFERENCES appeals(appeal_id) ON DELETE SET NULL,
    INDEX idx_investigations_employee (employee_id),
    INDEX idx_investigations_authority (higher_authority_id),
    INDEX idx_investigations_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. AUDIT LOGS TABLE
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NULL,
    entity_id INT NULL,
    description TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) 
        REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_audit_user (user_id),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. PROJECTS TABLE
CREATE TABLE IF NOT EXISTS projects (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    description TEXT,
    progress INT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    priority VARCHAR(50),
    due_date DATE NULL,
    milestones_completed INT DEFAULT 0,
    milestones_total INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_projects_employee FOREIGN KEY (employee_id) 
        REFERENCES employees(employee_id) ON DELETE CASCADE,
    INDEX idx_projects_employee (employee_id),
    INDEX idx_projects_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. LOGIN OTPS (2FA EMAIL VERIFICATION)
CREATE TABLE IF NOT EXISTS login_otps (
    otp_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    otp_hash VARCHAR(255) NOT NULL,
    expires_at DATETIME NOT NULL,
    attempts INT DEFAULT 0,
    verified_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_otps_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_expires (user_id, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. CLAIMS TABLE (EMPLOYEE WORK CLAIMS)
CREATE TABLE IF NOT EXISTS claims (
    claim_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    appraisal_period VARCHAR(50) NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    work_date DATE NULL,
    document_reference VARCHAR(255) NULL,
    status ENUM('SUBMITTED', 'APPROVED', 'REJECTED') DEFAULT 'SUBMITTED',
    manager_id INT NULL,
    manager_comments TEXT NULL,
    reviewed_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_claims_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_claims_manager FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_claim_employee (employee_id),
    INDEX idx_claim_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. PROJECT TASKS TABLE
CREATE TABLE IF NOT EXISTS project_tasks (
    task_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    employee_id INT NOT NULL,
    assigned_by INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    due_date DATE NULL,
    status ENUM('PENDING', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED') DEFAULT 'PENDING',
    employee_result TEXT NULL,
    employee_reason TEXT NULL,
    submitted_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_tasks_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT fk_tasks_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_tasks_assigned_by FOREIGN KEY (assigned_by) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_task_emp (employee_id),
    INDEX idx_task_proj (project_id),
    INDEX idx_task_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13. TASK REVIEWS TABLE
CREATE TABLE IF NOT EXISTS task_reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL UNIQUE,
    manager_id INT NOT NULL,
    rating DECIMAL(3,2) NOT NULL,
    comments TEXT NULL,
    reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_reviews_task FOREIGN KEY (task_id) REFERENCES project_tasks(task_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_manager FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_task_rating (rating)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 14. PROMOTION REQUESTS TABLE
CREATE TABLE IF NOT EXISTS promotion_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    appraisal_id INT NULL,
    manager_id INT NULL,
    hr_id INT NULL,
    request_type VARCHAR(50) DEFAULT 'PROMOTION',
    reason TEXT NOT NULL,
    document_reference VARCHAR(255) NULL,
    status ENUM('SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED') DEFAULT 'SUBMITTED',
    hr_response TEXT NULL,
    task_average DECIMAL(3,2) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_prom_req_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_prom_req_appraisal FOREIGN KEY (appraisal_id) REFERENCES appraisals(appraisal_id) ON DELETE SET NULL,
    CONSTRAINT fk_prom_req_manager FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT fk_prom_req_hr FOREIGN KEY (hr_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_prom_req_emp (employee_id),
    INDEX idx_prom_req_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15. PROMOTIONS HISTORY TABLE
CREATE TABLE IF NOT EXISTS promotions (
    promotion_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    promotion_request_id INT NULL,
    appraisal_id INT NULL,
    previous_role VARCHAR(50) NOT NULL,
    new_role VARCHAR(50) NOT NULL,
    previous_designation VARCHAR(100) NULL,
    new_designation VARCHAR(100) NOT NULL,
    approved_by INT NOT NULL,
    task_average DECIMAL(3,2) NULL,
    effective_date DATE NOT NULL,
    comments TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_prom_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_prom_request FOREIGN KEY (promotion_request_id) REFERENCES promotion_requests(request_id) ON DELETE SET NULL,
    CONSTRAINT fk_prom_appraisal FOREIGN KEY (appraisal_id) REFERENCES appraisals(appraisal_id) ON DELETE SET NULL,
    CONSTRAINT fk_prom_approved_by FOREIGN KEY (approved_by) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_prom_emp (employee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
