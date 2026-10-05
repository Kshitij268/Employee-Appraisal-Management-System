"""
Employee Appraisal Management System (EAMS)
Database Access Layer
"""

import datetime
import hashlib
import os
import secrets
from datetime import datetime, timedelta
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config


def get_db_connection(use_database=True):
    """
    Establish and return a MySQL connection.
    If use_database is False, connects to the server without selecting a specific database.
    """
    config = {
        "host": Config.DB_HOST,
        "port": Config.DB_PORT,
        "user": Config.DB_USER,
        "password": Config.DB_PASSWORD,
        "charset": "utf8mb4",
        "use_unicode": True,
        "autocommit": False
    }
    if use_database:
        config["database"] = Config.DB_NAME

    return mysql.connector.connect(**config)


def init_db():
    """Create the configured database and all project tables when missing.

    This is deliberately safe to run repeatedly.  The setup script has always
    called this function, but it was missing, which made first-time setup fail
    before a user could reach the sign-in screen.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "sql", "schema.sql")
    if not os.path.isfile(schema_path):
        raise FileNotFoundError("Database schema file was not found.")

    with open(schema_path, "r", encoding="utf-8") as schema_file:
        schema = schema_file.read()

    # schema.sql is intentionally plain SQL (no stored procedures), so simple
    # statement splitting is reliable here.  Honour a custom DB_NAME rather
    # than silently creating only the historical default database.
    schema = schema.replace("CREATE DATABASE IF NOT EXISTS employee_appraisal", f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}`")
    schema = schema.replace("USE employee_appraisal", f"USE `{Config.DB_NAME}`")
    conn = get_db_connection(use_database=False)
    cursor = conn.cursor()
    try:
        for statement in schema.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False, return_lastrowid=False):
    """
    Utility function to execute a parameterized SQL query safely.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        result = None
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
            
        if commit:
            conn.commit()
            if return_lastrowid:
                result = cursor.lastrowid
                
        return result
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# SCHEMA MIGRATION / SELF-HEALING
# ============================================================

def migrate_db_schema():
    """
    Ensures active MySQL tables match the latest schema requirements:
    - Adds `age` and `address` to `employees` if missing
    - Adds assignment columns required by the appraisal and appeal workflows
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Check and add columns to employees table
        cursor.execute("DESCRIBE employees")
        emp_cols = [row["Field"].lower() for row in cursor.fetchall()]

        if "age" not in emp_cols:
            cursor.execute("ALTER TABLE employees ADD COLUMN age INT NULL AFTER employee_code")
            conn.commit()
            print("[SCHEMA] Added 'age' column to employees table.")

        if "address" not in emp_cols:
            cursor.execute("ALTER TABLE employees ADD COLUMN address TEXT NULL AFTER age")
            conn.commit()
            print("[SCHEMA] Added 'address' column to employees table.")

        # 2. Check and add columns to appraisals table.
        cursor.execute("DESCRIBE appraisals")
        appraisal_cols = [row["Field"].lower() for row in cursor.fetchall()]
        if "hr_id" not in appraisal_cols:
            cursor.execute("ALTER TABLE appraisals ADD COLUMN hr_id INT NULL AFTER manager_id")
            conn.commit()
            print("[SCHEMA] Added 'hr_id' column to appraisals table.")

        # 3. Check and add columns to appeals table.
        cursor.execute("DESCRIBE appeals")
        appeal_cols = [row["Field"].lower() for row in cursor.fetchall()]
        if "manager_id" not in appeal_cols:
            cursor.execute("ALTER TABLE appeals ADD COLUMN manager_id INT NULL AFTER employee_id")
            conn.commit()
            print("[SCHEMA] Added 'manager_id' column to appeals table.")
        if "hr_id" not in appeal_cols:
            cursor.execute("ALTER TABLE appeals ADD COLUMN hr_id INT NULL AFTER manager_id")
            conn.commit()
            print("[SCHEMA] Added 'hr_id' column to appeals table.")

        # 4. Check and add columns to investigations table
        cursor.execute("DESCRIBE investigations")
        inv_cols = [row["Field"].lower() for row in cursor.fetchall()]

        if "appraisal_id" not in inv_cols:
            cursor.execute("ALTER TABLE investigations ADD COLUMN appraisal_id INT NULL AFTER higher_authority_id")
            conn.commit()
            print("[SCHEMA] Added 'appraisal_id' column to investigations table.")

        if "appeal_id" not in inv_cols:
            cursor.execute("ALTER TABLE investigations ADD COLUMN appeal_id INT NULL AFTER appraisal_id")
            conn.commit()
            print("[SCHEMA] Added 'appeal_id' column to investigations table.")

        # 5. Check and add must_change_password + email_verified to users table
        cursor.execute("DESCRIBE users")
        user_cols = [row["Field"].lower() for row in cursor.fetchall()]
        if "must_change_password" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN must_change_password TINYINT(1) DEFAULT 0 AFTER role")
            conn.commit()
            print("[SCHEMA] Added 'must_change_password' column to users table.")
        if "email_verified" not in user_cols:
            # Pre-existing users (seeded accounts) are considered already verified
            cursor.execute("ALTER TABLE users ADD COLUMN email_verified TINYINT(1) DEFAULT 0 AFTER must_change_password")
            conn.commit()
            # Mark all existing (pre-seeded) accounts as verified so they can log in without OTP
            cursor.execute("UPDATE users SET email_verified = 1")
            conn.commit()
            print("[SCHEMA] Added 'email_verified' column to users table. Pre-existing accounts marked as verified.")

        # 6. Create login_otps table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_otps (
                otp_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                otp_hash VARCHAR(255) NOT NULL,
                expires_at DATETIME NOT NULL,
                attempts INT DEFAULT 0,
                verified_at DATETIME NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                INDEX idx_user_expires (user_id, expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()

        # 7. Create claims table
        cursor.execute("""
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
                FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
                FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE SET NULL,
                INDEX idx_claim_employee (employee_id),
                INDEX idx_claim_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()

        # 8. Create project_tasks table
        cursor.execute("""
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
                FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_by) REFERENCES users(user_id) ON DELETE CASCADE,
                INDEX idx_task_emp (employee_id),
                INDEX idx_task_proj (project_id),
                INDEX idx_task_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()

        # 9. Create task_reviews table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_reviews (
                review_id INT AUTO_INCREMENT PRIMARY KEY,
                task_id INT NOT NULL UNIQUE,
                manager_id INT NOT NULL,
                rating DECIMAL(3,2) NOT NULL,
                comments TEXT NULL,
                reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES project_tasks(task_id) ON DELETE CASCADE,
                FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE CASCADE,
                INDEX idx_task_rating (rating)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()

        # 10. Create promotion_requests table
        cursor.execute("""
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
                FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
                FOREIGN KEY (appraisal_id) REFERENCES appraisals(appraisal_id) ON DELETE SET NULL,
                FOREIGN KEY (manager_id) REFERENCES users(user_id) ON DELETE SET NULL,
                FOREIGN KEY (hr_id) REFERENCES users(user_id) ON DELETE SET NULL,
                INDEX idx_prom_req_emp (employee_id),
                INDEX idx_prom_req_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()

        # 11. Create promotions table
        cursor.execute("""
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
                FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
                FOREIGN KEY (promotion_request_id) REFERENCES promotion_requests(request_id) ON DELETE SET NULL,
                FOREIGN KEY (appraisal_id) REFERENCES appraisals(appraisal_id) ON DELETE SET NULL,
                FOREIGN KEY (approved_by) REFERENCES users(user_id) ON DELETE CASCADE,
                INDEX idx_prom_emp (employee_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()

        # 12. Normalize existing emails to @gmail.com
        cursor.execute("UPDATE users SET email = REPLACE(email, '@example.com', '@gmail.com') WHERE email LIKE '%@example.com'")
        cursor.execute("UPDATE users SET email = REPLACE(email, '@eams.local', '@gmail.com') WHERE email LIKE '%@eams.local'")
        conn.commit()

        # 13. Ensure default System Administrator account with admin@gmail.com
        cursor.execute("SELECT user_id, role, email FROM users WHERE role = 'administrator' OR email = 'admin@gmail.com'")
        admin_row = cursor.fetchone()
        if not admin_row:
            cursor.execute("""
                INSERT INTO users (name, email, password_hash, role, email_verified)
                VALUES (%s, %s, %s, 'administrator', 1)
            """, ("System Administrator", "admin@gmail.com", generate_password_hash("Password@123")))
            conn.commit()
            print("[SCHEMA] Seeded default administrator (admin@gmail.com / Password@123).")
        else:
            cursor.execute("UPDATE users SET email = 'admin@gmail.com', role = 'administrator' WHERE user_id = %s", (admin_row["user_id"],))
            conn.commit()

        # 14. Seed sample tasks and task reviews for demonstration if none exist
        cursor.execute("SELECT COUNT(*) as cnt FROM project_tasks")
        tasks_cnt = cursor.fetchone().get("cnt", 0)
        if tasks_cnt == 0:
            cursor.execute("SELECT employee_id FROM employees WHERE user_id = 3")
            emp3 = cursor.fetchone()
            emp3_id = emp3["employee_id"] if emp3 else 3
            cursor.execute("SELECT project_id FROM projects LIMIT 1")
            proj = cursor.fetchone()
            proj_id = proj["project_id"] if proj else 1
            cursor.execute("SELECT user_id FROM users WHERE role = 'manager' LIMIT 1")
            mgr = cursor.fetchone()
            mgr_id = mgr["user_id"] if mgr else 2

            sample_tasks = [
                (proj_id, emp3_id, mgr_id, "Design Enterprise 2FA & Auth Security Core", "Architect tokenless session security and strict credential validation.", "2026-10-15", "COMPLETED", "Completed all authentication workflows and verified test suites.", None),
                (proj_id, emp3_id, mgr_id, "Database Query Optimization & Multi-Role Indexing", "Optimize complex relational queries and index access paths.", "2026-10-20", "COMPLETED", "Achieved sub-10ms response times across all aggregated tables.", None),
                (proj_id, emp3_id, mgr_id, "Cloud Microservice Scalability & Resilience", "Configure automated failover mechanisms and resilient logging.", "2026-11-01", "COMPLETED", "Zero-downtime architecture validated in staging.", None)
            ]
            for t in sample_tasks:
                cursor.execute("""
                    INSERT INTO project_tasks (project_id, employee_id, assigned_by, title, description, due_date, status, employee_result, employee_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, t)
                t_id = cursor.lastrowid
                rating = 4.80 if "2FA" in t[3] else (4.70 if "Database" in t[3] else 4.90)
                cursor.execute("""
                    INSERT INTO task_reviews (task_id, manager_id, rating, comments)
                    VALUES (%s, %s, %s, %s)
                """, (t_id, mgr_id, rating, "Exceptional delivery quality and proactive execution."))
            conn.commit()
            print("[SCHEMA] Seeded sample project tasks and task reviews for David Chen.")

        print("[SCHEMA] Migrations completed successfully.")

    except Exception as e:
        print(f"[SCHEMA MIGRATION WARNING] {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# AUDIT LOGGING
# ============================================================

def create_audit_log(user_id, action, entity_type=None, entity_id=None, description=None):
    """
    Record an append-only audit log entry for system accountability.
    """
    sql = """
        INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description)
        VALUES (%s, %s, %s, %s, %s)
    """
    try:
        return execute_query(sql, (user_id, action, entity_type, entity_id, description), commit=True, return_lastrowid=True)
    except Exception as e:
        print(f"[AUDIT LOG ERROR] Failed to record audit log: {e}")
        return None


def get_audit_logs(limit=100, user_id=None):
    """
    Retrieve recent audit logs with joined user details.
    """
    if user_id:
        sql = """
            SELECT a.*, u.name as user_name, u.role as user_role, u.email as user_email
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.user_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s
        """
        return execute_query(sql, (user_id, limit), fetchall=True)
    else:
        sql = """
            SELECT a.*, u.name as user_name, u.role as user_role, u.email as user_email
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.user_id
            ORDER BY a.created_at DESC
            LIMIT %s
        """
        return execute_query(sql, (limit,), fetchall=True)


# ============================================================
# USERS & AUTHENTICATION
# ============================================================

def get_user_by_email(email):
    """Retrieve user record by email address."""
    sql = "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)"
    return execute_query(sql, (email,), fetchone=True)


def get_user_by_id(user_id):
    """Retrieve user record by user_id."""
    sql = "SELECT * FROM users WHERE user_id = %s"
    return execute_query(sql, (user_id,), fetchone=True)


def get_users_by_roles(roles):
    """Return users in the supplied roles, including useful profile details."""
    if not roles:
        return []
    placeholders = ", ".join(["%s"] * len(roles))
    sql = f"""
        SELECT u.user_id, u.name, u.email, u.role, e.department, e.designation
        FROM users u
        LEFT JOIN employees e ON e.user_id = u.user_id
        WHERE LOWER(u.role) IN ({placeholders})
        ORDER BY u.name ASC
    """
    return execute_query(sql, tuple(role.lower() for role in roles), fetchall=True)


def is_user_in_roles(user_id, roles):
    """Check a user role in the database rather than trusting a submitted id."""
    if not user_id or not roles:
        return False
    placeholders = ", ".join(["%s"] * len(roles))
    sql = f"SELECT user_id FROM users WHERE user_id = %s AND LOWER(role) IN ({placeholders})"
    return bool(execute_query(sql, (user_id, *(role.lower() for role in roles)), fetchone=True))


def get_primary_hr_user():
    """Return the configured HR authority, supporting legacy admin accounts."""
    users = get_users_by_roles(("hr", "admin"))
    return users[0] if users else None


def create_user(name, email, password_hash, role='employee'):
    """Create a new user account."""
    sql = """
        INSERT INTO users (name, email, password_hash, role)
        VALUES (%s, %s, %s, %s)
    """
    return execute_query(sql, (name, email, password_hash, role), commit=True, return_lastrowid=True)


def update_user(user_id, name=None, password_hash=None):
    """Update user credentials or name."""
    updates = []
    params = []
    if name:
        updates.append("name = %s")
        params.append(name)
    if password_hash:
        updates.append("password_hash = %s")
        params.append(password_hash)
        
    if not updates:
        return False
        
    params.append(user_id)
    sql = f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s"
    execute_query(sql, tuple(params), commit=True)
    return True


def change_user_password(user_id, current_password, new_password_hash):
    """
    Verifies user's current password and updates with the new password hash.
    Returns (success: bool, message: str).
    """
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found."
    
    if not check_password_hash(user["password_hash"], current_password):
        return False, "Current password is incorrect."

    sql = "UPDATE users SET password_hash = %s WHERE user_id = %s"
    execute_query(sql, (new_password_hash, user_id), commit=True)
    create_audit_log(user_id, "CHANGE_PASSWORD", "USER", user_id, "User changed account password.")
    return True, "Password changed successfully."


# ============================================================
# EMPLOYEES & PROFILES
# ============================================================

def get_employee_by_user_id(user_id):
    """
    Retrieve employee profile joined with user info and manager info.
    If no employee record exists (e.g. for an admin/manager user created outside transaction), returns minimal profile.
    """
    sql = """
        SELECT e.*, u.name, u.email, u.role,
               m.name as manager_name, m.email as manager_email
        FROM users u
        LEFT JOIN employees e ON u.user_id = e.user_id
        LEFT JOIN users m ON e.manager_id = m.user_id
        WHERE u.user_id = %s
    """
    emp = execute_query(sql, (user_id,), fetchone=True)
    return emp


def get_employee_by_id(employee_id):
    """
    Retrieve employee profile by employee_id.
    """
    sql = """
        SELECT e.*, u.name, u.email, u.role,
               m.name as manager_name, m.email as manager_email
        FROM employees e
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON e.manager_id = m.user_id
        WHERE e.employee_id = %s
    """
    return execute_query(sql, (employee_id,), fetchone=True)


def get_employees(search=None, department=None):
    """
    Retrieve all employees with optional search and department filters for HR.
    """
    sql = """
        SELECT e.*, u.name, u.email, u.role,
               m.name as manager_name
        FROM employees e
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON e.manager_id = m.user_id
        WHERE 1=1
    """
    params = []
    if department and department.strip():
        sql += " AND e.department = %s"
        params.append(department.strip())
    if search and search.strip():
        term = f"%{search.strip()}%"
        sql += " AND (u.name LIKE %s OR u.email LIKE %s OR e.employee_code LIKE %s OR e.designation LIKE %s)"
        params.extend([term, term, term, term])
        
    sql += " ORDER BY u.name ASC"
    return execute_query(sql, tuple(params), fetchall=True)


def create_employee_transaction(name, email, password_hash, role='employee', employee_code=None,
                                age=None, address=None, department='Engineering', designation='Staff',
                                phone=None, location=None, joining_date=None, manager_id=None):
    """
    Atomic transaction: Create user account and corresponding employee record.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Insert into users
        user_sql = """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(user_sql, (name, email, password_hash, role))
        user_id = cursor.lastrowid
        
        # Generate employee code if missing
        if not employee_code:
            employee_code = f"EMP-{role[:3].upper()}-{user_id:04d}"

        # 2. Insert into employees
        emp_sql = """
            INSERT INTO employees (user_id, employee_code, age, address, department, designation, phone, location, joining_date, manager_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(emp_sql, (user_id, employee_code, age, address, department, designation, phone, location, joining_date, manager_id))
        employee_id = cursor.lastrowid
        
        conn.commit()
        return {"user_id": user_id, "employee_id": employee_id, "employee_code": employee_code}
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def update_profile(user_id, name=None, age=None, address=None, phone=None, location=None, department=None, designation=None):
    """
    Universal profile update for the logged-in user.
    Updates `users` table for name and `employees` table for personal details.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if name:
            cursor.execute("UPDATE users SET name = %s WHERE user_id = %s", (name, user_id))

        # Check if employee record exists
        cursor.execute("SELECT employee_id FROM employees WHERE user_id = %s", (user_id,))
        emp = cursor.fetchone()

        if emp:
            emp_id = emp["employee_id"]
            updates = []
            params = []
            if age is not None:
                updates.append("age = %s")
                params.append(age if age != '' else None)
            if address is not None:
                updates.append("address = %s")
                params.append(address)
            if phone is not None:
                updates.append("phone = %s")
                params.append(phone)
            if location is not None:
                updates.append("location = %s")
                params.append(location)
            if department is not None:
                updates.append("department = %s")
                params.append(department)
            if designation is not None:
                updates.append("designation = %s")
                params.append(designation)

            if updates:
                params.append(emp_id)
                sql = f"UPDATE employees SET {', '.join(updates)} WHERE employee_id = %s"
                cursor.execute(sql, tuple(params))
        else:
            # Create a corresponding employee record if user didn't have one
            code = f"EMP-USR-{user_id:04d}"
            cursor.execute("""
                INSERT INTO employees (user_id, employee_code, age, address, phone, location, department, designation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, code, age if age != '' else None, address, phone, location, department or 'General', designation or 'Staff'))

        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def update_employee(employee_id, department=None, designation=None, phone=None, location=None, age=None, address=None, manager_id=None):
    """Update employee details (HR/Admin management)."""
    updates = []
    params = []
    if department is not None:
        updates.append("department = %s")
        params.append(department)
    if designation is not None:
        updates.append("designation = %s")
        params.append(designation)
    if phone is not None:
        updates.append("phone = %s")
        params.append(phone)
    if location is not None:
        updates.append("location = %s")
        params.append(location)
    if age is not None:
        updates.append("age = %s")
        params.append(age if age != '' else None)
    if address is not None:
        updates.append("address = %s")
        params.append(address)
    if manager_id is not None:
        updates.append("manager_id = %s")
        params.append(manager_id if manager_id != 0 else None)

    if not updates:
        return False

    params.append(employee_id)
    sql = f"UPDATE employees SET {', '.join(updates)} WHERE employee_id = %s"
    execute_query(sql, tuple(params), commit=True)
    return True


def get_team_members(manager_user_id):
    """
    Retrieve direct reports for a given manager user_id.
    """
    sql = """
        SELECT e.*, u.name, u.email,
            (SELECT status FROM appraisals WHERE employee_id = e.employee_id ORDER BY created_at DESC LIMIT 1) as latest_appraisal_status,
            (SELECT overall_rating FROM appraisals WHERE employee_id = e.employee_id ORDER BY created_at DESC LIMIT 1) as latest_appraisal_rating,
            COALESCE((SELECT AVG(progress) FROM projects WHERE employee_id = e.employee_id), 0) as avg_project_progress,
            (SELECT COUNT(*) FROM projects WHERE employee_id = e.employee_id) as total_projects
        FROM employees e
        JOIN users u ON e.user_id = u.user_id
        WHERE e.manager_id = %s
        ORDER BY u.name ASC
    """
    return execute_query(sql, (manager_user_id,), fetchall=True)


# ============================================================
# PROJECTS
# ============================================================

def get_projects(employee_id=None):
    """Retrieve projects for a specific employee or all projects."""
    if employee_id:
        sql = """
            SELECT p.*, u.name as employee_name, e.employee_code, e.department
            FROM projects p
            JOIN employees e ON p.employee_id = e.employee_id
            JOIN users u ON e.user_id = u.user_id
            WHERE p.employee_id = %s
            ORDER BY p.created_at DESC
        """
        return execute_query(sql, (employee_id,), fetchall=True)
    else:
        sql = """
            SELECT p.*, u.name as employee_name, e.employee_code, e.department
            FROM projects p
            JOIN employees e ON p.employee_id = e.employee_id
            JOIN users u ON e.user_id = u.user_id
            ORDER BY p.created_at DESC
        """
        return execute_query(sql, fetchall=True)


def get_project_by_id(project_id):
    """Retrieve a single project record."""
    sql = """
        SELECT p.*, u.name as employee_name, e.employee_code, e.user_id as employee_user_id
        FROM projects p
        JOIN employees e ON p.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        WHERE p.project_id = %s
    """
    return execute_query(sql, (project_id,), fetchone=True)


def create_project(employee_id, name, category, description, progress=0, status='pending', priority='Medium', due_date=None, milestones_completed=0, milestones_total=0):
    """Insert a new project."""
    sql = """
        INSERT INTO projects (employee_id, name, category, description, progress, status, priority, due_date, milestones_completed, milestones_total)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(sql, (employee_id, name, category, description, progress, status, priority, due_date, milestones_completed, milestones_total), commit=True, return_lastrowid=True)


def update_project(project_id, name, category, description, progress, status, priority, due_date, milestones_completed, milestones_total):
    """Update an existing project."""
    sql = """
        UPDATE projects
        SET name = %s, category = %s, description = %s, progress = %s, status = %s, priority = %s, due_date = %s, milestones_completed = %s, milestones_total = %s
        WHERE project_id = %s
    """
    execute_query(sql, (name, category, description, progress, status, priority, due_date, milestones_completed, milestones_total, project_id), commit=True)
    return True


def delete_project(project_id):
    """Delete a project record."""
    sql = "DELETE FROM projects WHERE project_id = %s"
    execute_query(sql, (project_id,), commit=True)
    return True


# ============================================================
# APPRAISALS
# ============================================================

def get_appraisals(employee_id=None, manager_id=None):
    """
    Retrieve appraisals filtered by employee or manager, or all for HR.
    """
    sql = """
        SELECT a.*, 
               u.name as employee_name, u.email as employee_email, e.department, e.designation, e.employee_code, e.user_id as employee_user_id,
               m.name as manager_name
        FROM appraisals a
        JOIN employees e ON a.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON a.manager_id = m.user_id
        LEFT JOIN users hr ON a.hr_id = hr.user_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        sql += " AND a.employee_id = %s"
        params.append(employee_id)
    if manager_id:
        # Legacy records did not store the per-appraisal manager.  Only those
        # records may use the employee's default reporting manager as fallback.
        sql += " AND (a.manager_id = %s OR (a.manager_id IS NULL AND e.manager_id = %s))"
        params.extend([manager_id, manager_id])

    sql += " ORDER BY a.created_at DESC"
    return execute_query(sql, tuple(params) if params else None, fetchall=True)


def get_appraisal_by_id(appraisal_id):
    """Retrieve appraisal record by appraisal_id."""
    sql = """
        SELECT a.*, 
               u.name as employee_name, u.email as employee_email, e.department, e.designation, e.employee_code, e.user_id as employee_user_id, e.manager_id as direct_manager_id,
               m.name as manager_name, hr.name as hr_name
        FROM appraisals a
        JOIN employees e ON a.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON a.manager_id = m.user_id
        LEFT JOIN users hr ON a.hr_id = hr.user_id
        WHERE a.appraisal_id = %s
    """
    return execute_query(sql, (appraisal_id,), fetchone=True)


def create_appraisal(employee_id, manager_id, hr_id, appraisal_period, self_rating, employee_comments, status='UNDER_REVIEW'):
    """Insert a new appraisal record with status UNDER_REVIEW."""
    sql = """
        INSERT INTO appraisals (employee_id, manager_id, hr_id, appraisal_period, self_rating, employee_comments, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    return execute_query(sql, (employee_id, manager_id, hr_id, appraisal_period, self_rating, employee_comments, status), commit=True, return_lastrowid=True)


def review_appraisal_transaction(appraisal_id, manager_id, overall_rating, manager_comments, status):
    """
    Review appraisal with transactional integrity (APPROVED, REJECTED, CHANGES_REQUESTED).
    """
    sql = """
        UPDATE appraisals
        SET overall_rating = %s, manager_comments = %s, status = %s, updated_at = CURRENT_TIMESTAMP
        WHERE appraisal_id = %s
    """
    execute_query(sql, (overall_rating, manager_comments, status, appraisal_id), commit=True)
    return True


# ============================================================
# DOCUMENTS & VERIFICATION
# ============================================================

def get_documents(employee_id=None, status=None, manager_user_id=None):
    """
    Retrieve documents. If manager_user_id provided, returns documents belonging to direct reports.
    """
    sql = """
        SELECT d.*, u.name as employee_name, e.department, e.employee_code
        FROM documents d
        JOIN employees e ON d.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        sql += " AND d.employee_id = %s"
        params.append(employee_id)
    if status:
        sql += " AND d.status = %s"
        params.append(status)
    if manager_user_id:
        sql += " AND e.manager_id = %s"
        params.append(manager_user_id)

    sql += " ORDER BY d.submitted_at DESC"
    return execute_query(sql, tuple(params) if params else None, fetchall=True)


def get_document_by_id(document_id):
    """Retrieve document by ID."""
    sql = """
        SELECT d.*, e.user_id as employee_user_id, e.manager_id
        FROM documents d
        JOIN employees e ON d.employee_id = e.employee_id
        WHERE d.document_id = %s
    """
    return execute_query(sql, (document_id,), fetchone=True)


def create_document(employee_id, document_type, document_name, document_path):
    """Insert uploaded document record."""
    sql = """
        INSERT INTO documents (employee_id, document_type, document_name, document_path, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """
    return execute_query(sql, (employee_id, document_type, document_name, document_path), commit=True, return_lastrowid=True)


def resubmit_document(document_id, document_name, document_path):
    """Update existing document with new file and set status back to pending."""
    sql = """
        UPDATE documents
        SET document_name = %s, document_path = %s, status = 'pending', manager_comments = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE document_id = %s
    """
    execute_query(sql, (document_name, document_path, document_id), commit=True)
    return True


def review_document_transaction(document_id, manager_id, action, comments=None):
    """
    Atomic transaction: Update document status and record verification entry in document_verification.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Update document status and comments
        doc_sql = """
            UPDATE documents
            SET status = %s, manager_comments = %s, updated_at = CURRENT_TIMESTAMP
            WHERE document_id = %s
        """
        cursor.execute(doc_sql, (action, comments, document_id))
        
        # 2. Insert into document_verification
        verif_sql = """
            INSERT INTO document_verification (document_id, manager_id, action, comments)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(verif_sql, (document_id, manager_id, action, comments))
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# APPEALS
# ============================================================

def get_appeals(employee_id=None, manager_user_id=None):
    """
    Retrieve appeals.
    """
    sql = """
        SELECT a.*, 
               u.name as employee_name, u.email as employee_email, e.department, e.employee_code,
               ap.appraisal_period, ap.overall_rating, ap.status as appraisal_status, ap.manager_comments as appraisal_manager_comments,
               m.name as manager_name, hr.name as hr_name
        FROM appeals a
        JOIN employees e ON a.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        JOIN appraisals ap ON a.appraisal_id = ap.appraisal_id
        LEFT JOIN users m ON a.manager_id = m.user_id
        LEFT JOIN users hr ON a.hr_id = hr.user_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        sql += " AND a.employee_id = %s"
        params.append(employee_id)
    if manager_user_id:
        sql += " AND (a.manager_id = %s OR (a.manager_id IS NULL AND e.manager_id = %s))"
        params.extend([manager_user_id, manager_user_id])

    sql += " ORDER BY a.created_at DESC"
    return execute_query(sql, tuple(params) if params else None, fetchall=True)


def get_appeal_by_id(appeal_id):
    """Retrieve appeal by ID."""
    sql = """
        SELECT a.*, e.user_id as employee_user_id, e.manager_id as direct_manager_id, u.name as employee_name,
               ap.appraisal_period, ap.overall_rating, ap.status as appraisal_status, ap.manager_comments as appraisal_manager_comments
        FROM appeals a
        JOIN employees e ON a.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        JOIN appraisals ap ON a.appraisal_id = ap.appraisal_id
        WHERE a.appeal_id = %s
    """
    return execute_query(sql, (appeal_id,), fetchone=True)


def create_appeal(appraisal_id, employee_id, manager_id, hr_id, reason):
    """Submit an appeal against an appraisal."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Insert into appeals
        cursor.execute("""
            INSERT INTO appeals (appraisal_id, employee_id, manager_id, hr_id, reason, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (appraisal_id, employee_id, manager_id, hr_id, reason))
        appeal_id = cursor.lastrowid

        # 2. Update appraisal status to APPEALED
        cursor.execute("UPDATE appraisals SET status = 'APPEALED' WHERE appraisal_id = %s", (appraisal_id,))

        conn.commit()
        return appeal_id
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def review_appeal(appeal_id, status, manager_response, appraisal_status=None):
    """
    Review and update appeal status with manager response.
    Optionally updates the associated appraisal status (e.g. APPROVED or REJECTED).
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE appeals
            SET status = %s, manager_response = %s, updated_at = CURRENT_TIMESTAMP
            WHERE appeal_id = %s
        """, (status, manager_response, appeal_id))

        if appraisal_status:
            cursor.execute("SELECT appraisal_id FROM appeals WHERE appeal_id = %s", (appeal_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE appraisals SET status = %s WHERE appraisal_id = %s", (appraisal_status, row["appraisal_id"]))

        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# INVESTIGATIONS / HR COMPLAINTS
# ============================================================

def get_investigations(employee_id=None, higher_authority_id=None):
    """
    Retrieve investigations/complaints for employee or HR administration.
    """
    sql = """
        SELECT i.*, 
               u.name as employee_name, u.email as employee_email, e.department, e.employee_code,
               m.name as manager_name,
               hr.name as reviewer_name,
               ap.appraisal_period, ap.status as appraisal_status,
               app.reason as appeal_reason, app.status as appeal_status
        FROM investigations i
        JOIN employees e ON i.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON i.manager_id = m.user_id
        LEFT JOIN users hr ON i.reviewed_by = hr.user_id
        LEFT JOIN appraisals ap ON i.appraisal_id = ap.appraisal_id
        LEFT JOIN appeals app ON i.appeal_id = app.appeal_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        sql += " AND i.employee_id = %s"
        params.append(employee_id)
    if higher_authority_id:
        sql += " AND (i.higher_authority_id = %s OR i.higher_authority_id IS NULL)"
        params.append(higher_authority_id)

    sql += " ORDER BY i.created_at DESC"
    return execute_query(sql, tuple(params) if params else None, fetchall=True)


def get_investigation_by_id(investigation_id):
    """Retrieve investigation by ID."""
    sql = """
        SELECT i.*, 
               u.name as employee_name, u.email as employee_email, e.department, e.employee_code, e.user_id as employee_user_id,
               m.name as manager_name,
               hr.name as reviewer_name,
               ap.appraisal_period, ap.status as appraisal_status,
               app.reason as appeal_reason, app.status as appeal_status
        FROM investigations i
        JOIN employees e ON i.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON i.manager_id = m.user_id
        LEFT JOIN users hr ON i.reviewed_by = hr.user_id
        LEFT JOIN appraisals ap ON i.appraisal_id = ap.appraisal_id
        LEFT JOIN appeals app ON i.appeal_id = app.appeal_id
        WHERE i.investigation_id = %s
    """
    return execute_query(sql, (investigation_id,), fetchone=True)


def create_investigation(employee_id, manager_id, higher_authority_id, issue_type, subject, description, evidence_details, appraisal_id=None, appeal_id=None):
    """Submit an escalated complaint/investigation to HR."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
            INSERT INTO investigations (employee_id, manager_id, higher_authority_id, appraisal_id, appeal_id, issue_type, subject, description, evidence_details, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """
        cursor.execute(sql, (employee_id, manager_id, higher_authority_id, appraisal_id, appeal_id, issue_type, subject, description, evidence_details))
        inv_id = cursor.lastrowid

        if appraisal_id:
            cursor.execute("UPDATE appraisals SET status = 'UNDER_HR_REVIEW' WHERE appraisal_id = %s", (appraisal_id,))

        conn.commit()
        return inv_id
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def review_investigation(investigation_id, status, authority_response, reviewed_by):
    """Review and resolve an investigation."""
    resolved_at = "CURRENT_TIMESTAMP" if "resolved" in status.lower() else "NULL"
    sql = f"""
        UPDATE investigations
        SET status = %s, authority_response = %s, reviewed_by = %s, resolved_at = {resolved_at}, updated_at = CURRENT_TIMESTAMP
        WHERE investigation_id = %s
    """
    execute_query(sql, (status, authority_response, reviewed_by, investigation_id), commit=True)
    return True


# ============================================================
# DASHBOARD & REPORTS (REAL SQL AGGREGATION - NO GOALS)
# ============================================================

def get_employee_dashboard_metrics(employee_id):
    """
    Aggregates real statistics for an employee's dashboard.
    """
    sql = """
        SELECT
            (SELECT status FROM appraisals WHERE employee_id = %s ORDER BY created_at DESC LIMIT 1) as appraisal_status,
            (SELECT self_rating FROM appraisals WHERE employee_id = %s ORDER BY created_at DESC LIMIT 1) as self_rating,
            (SELECT overall_rating FROM appraisals WHERE employee_id = %s ORDER BY created_at DESC LIMIT 1) as overall_rating,
            (SELECT COUNT(*) FROM projects WHERE employee_id = %s) as total_projects,
            (SELECT COUNT(*) FROM documents WHERE employee_id = %s) as total_documents,
            (SELECT COUNT(*) FROM documents WHERE employee_id = %s AND status = 'pending') as pending_documents,
            (SELECT COUNT(*) FROM appeals WHERE employee_id = %s) as total_appeals,
            (SELECT status FROM appeals WHERE employee_id = %s ORDER BY created_at DESC LIMIT 1) as latest_appeal_status,
            (SELECT COUNT(*) FROM investigations WHERE employee_id = %s) as total_investigations,
            (SELECT status FROM investigations WHERE employee_id = %s ORDER BY created_at DESC LIMIT 1) as latest_investigation_status
    """
    return execute_query(sql, (employee_id, employee_id, employee_id, employee_id, employee_id, employee_id, employee_id, employee_id, employee_id, employee_id), fetchone=True)


def get_manager_dashboard_metrics(manager_user_id):
    """
    Aggregates real metrics for a manager's direct reports.
    """
    sql = """
        SELECT
            (SELECT COUNT(*) FROM employees WHERE manager_id = %s) as direct_report_count,
            (SELECT COUNT(*) FROM appraisals a JOIN employees e ON a.employee_id = e.employee_id WHERE (a.manager_id = %s OR (a.manager_id IS NULL AND e.manager_id = %s)) AND a.status IN ('UNDER_REVIEW', 'submitted')) as pending_appraisals,
            (SELECT COUNT(*) FROM documents d JOIN employees e ON d.employee_id = e.employee_id WHERE e.manager_id = %s AND d.status = 'pending') as pending_documents,
            (SELECT COUNT(*) FROM appeals ap JOIN employees e ON ap.employee_id = e.employee_id WHERE (ap.manager_id = %s OR (ap.manager_id IS NULL AND e.manager_id = %s)) AND ap.status = 'pending') as pending_appeals,
            (SELECT COUNT(*) FROM projects p JOIN employees e ON p.employee_id = e.employee_id WHERE e.manager_id = %s) as total_team_projects,
            COALESCE((SELECT AVG(a.overall_rating) FROM appraisals a JOIN employees e ON a.employee_id = e.employee_id WHERE (a.manager_id = %s OR (a.manager_id IS NULL AND e.manager_id = %s)) AND a.overall_rating IS NOT NULL), 0) as avg_team_performance
    """
    return execute_query(sql, (manager_user_id, manager_user_id, manager_user_id, manager_user_id, manager_user_id, manager_user_id, manager_user_id, manager_user_id, manager_user_id), fetchone=True)


def get_hr_dashboard_metrics():
    """
    Aggregates organization-wide metrics for HR.
    """
    sql = """
        SELECT
            (SELECT COUNT(*) FROM employees) as total_employees,
            (SELECT COUNT(*) FROM users WHERE role = 'employee') as active_employees,
            (SELECT COUNT(*) FROM appraisals WHERE status IN ('APPROVED', 'approved', 'completed')) as completed_appraisals,
            (SELECT COUNT(*) FROM appraisals WHERE status IN ('UNDER_REVIEW', 'submitted')) as pending_appraisals,
            (SELECT COUNT(*) FROM appraisals) as total_appraisals,
            COALESCE((SELECT AVG(overall_rating) FROM appraisals WHERE overall_rating IS NOT NULL), 0) as avg_org_rating,
            (SELECT COUNT(*) FROM investigations WHERE status IN ('pending', 'under_investigation', 'UNDER_INVESTIGATION')) as pending_investigations,
            (SELECT COUNT(*) FROM projects) as total_projects
    """
    return execute_query(sql, fetchone=True)


def get_hr_reports():
    """
    Aggregates reporting metrics for HR Analytics using real SQL queries.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Summary statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_appraisals,
                SUM(CASE WHEN status IN ('APPROVED', 'approved', 'completed') THEN 1 ELSE 0 END) as completed_appraisals,
                SUM(CASE WHEN status IN ('UNDER_REVIEW', 'submitted') THEN 1 ELSE 0 END) as submitted_appraisals,
                SUM(CASE WHEN status IN ('REJECTED', 'rejected') THEN 1 ELSE 0 END) as rejected_appraisals,
                SUM(CASE WHEN status IN ('CHANGES_REQUESTED', 'changes_requested') THEN 1 ELSE 0 END) as changes_requested_appraisals,
                COALESCE(AVG(overall_rating), 0) as avg_rating
            FROM appraisals
        """)
        summary = cursor.fetchone() or {
            "total_appraisals": 0, "completed_appraisals": 0, "submitted_appraisals": 0,
            "rejected_appraisals": 0, "changes_requested_appraisals": 0, "avg_rating": 0
        }

        # 2. Rating distribution (buckets: 1-2, 2-3, 3-4, 4-5)
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN overall_rating >= 1.00 AND overall_rating < 2.00 THEN 1 ELSE 0 END) as bucket_1_2,
                SUM(CASE WHEN overall_rating >= 2.00 AND overall_rating < 3.00 THEN 1 ELSE 0 END) as bucket_2_3,
                SUM(CASE WHEN overall_rating >= 3.00 AND overall_rating < 4.00 THEN 1 ELSE 0 END) as bucket_3_4,
                SUM(CASE WHEN overall_rating >= 4.00 AND overall_rating <= 5.00 THEN 1 ELSE 0 END) as bucket_4_5
            FROM appraisals
            WHERE overall_rating IS NOT NULL
        """)
        rating_dist = cursor.fetchone() or {"bucket_1_2": 0, "bucket_2_3": 0, "bucket_3_4": 0, "bucket_4_5": 0}

        # 3. Department average rating and employee counts
        cursor.execute("""
            SELECT 
                e.department,
                COUNT(DISTINCT e.employee_id) as employee_count,
                COALESCE(AVG(a.overall_rating), 0) as avg_rating,
                COUNT(a.appraisal_id) as total_appraisals
            FROM employees e
            LEFT JOIN appraisals a ON e.employee_id = a.employee_id
            WHERE e.department IS NOT NULL
            GROUP BY e.department
            ORDER BY avg_rating DESC
        """)
        dept_ratings = cursor.fetchall() or []

        # 4. Project completion statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_projects,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_projects,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_projects,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_projects,
                COALESCE(AVG(progress), 0) as avg_progress,
                COALESCE(SUM(milestones_completed), 0) as completed_milestones,
                COALESCE(SUM(milestones_total), 0) as total_milestones
            FROM projects
        """)
        project_stats = cursor.fetchone() or {
            "total_projects": 0, "completed_projects": 0, "in_progress_projects": 0,
            "pending_projects": 0, "avg_progress": 0, "completed_milestones": 0, "total_milestones": 0
        }

        # 5. Recent audit activity
        cursor.execute("""
            SELECT a.action, COUNT(*) as action_count
            FROM audit_logs a
            GROUP BY a.action
            ORDER BY action_count DESC
            LIMIT 10
        """)
        audit_activity = cursor.fetchall() or []

        completion_rate = 0
        if summary.get("total_appraisals") and summary["total_appraisals"] > 0:
            completion_rate = round((summary["completed_appraisals"] / summary["total_appraisals"]) * 100, 1)

        return {
            "summary": summary,
            "completion_rate": completion_rate,
            "rating_distribution": rating_dist,
            "department_ratings": dept_ratings,
            "project_stats": project_stats,
            "audit_activity": audit_activity
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# SEED & INITIALIZATION
# ============================================================

def seed_db():
    """
    Seed initial development records if database is empty.
    Hashes passwords dynamically with Werkzeug.
    """
    migrate_db_schema()

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Seed exactly once: existing accounts are the source of truth and must
        # never be altered (especially password hashes) during application startup.
        cursor.execute("SELECT user_id, email, password_hash FROM users")
        existing_users = cursor.fetchall()
        if existing_users and len(existing_users) > 0:
            print("[DATABASE] Existing users detected; skipping development seed without changing any accounts.")
            # Ensure default administrator role account exists
            cursor.execute("SELECT user_id FROM users WHERE role = 'administrator'")
            admin_user = cursor.fetchone()
            if not admin_user:
                cursor.execute("""
                    INSERT INTO users (name, email, password_hash, role)
                    VALUES (%s, %s, %s, 'administrator')
                """, ("System Administrator", "admin@eams.local", generate_password_hash("Password@123")))
                conn.commit()
                print("[DATABASE] Provisioned default administrator account (admin@eams.local / Password@123).")
            return True

        print("[DATABASE] Seeding development dataset...")
        pwd_hash = generate_password_hash("Password@123")

        # 1. Users
        users_data = [
            (1, "Sarah Jenkins", "hr@example.com", pwd_hash, "hr"),
            (2, "Alex Rivera", "manager@example.com", pwd_hash, "manager"),
            (3, "David Chen", "employee@example.com", pwd_hash, "employee"),
            (4, "Emily Watson", "emily.watson@example.com", pwd_hash, "employee"),
            (5, "Michael Brown", "michael.brown@example.com", pwd_hash, "employee"),
            (6, "System Administrator", "admin@eams.local", pwd_hash, "administrator")
        ]
        cursor.executemany(
            "INSERT INTO users (user_id, name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            users_data
        )

        # 2. Employees
        emp_data = [
            (1, 1, "EMP-HR-001", 38, "100 Broadway, New York, NY", "Human Resources", "HR Director", "+1 (555) 010-001", "Headquarters - New York", "2021-03-15", None),
            (2, 2, "EMP-ENG-002", 42, "456 Market St, San Jose, CA", "Engineering", "Engineering Manager", "+1 (555) 010-002", "Headquarters - New York", "2021-06-01", None),
            (3, 3, "EMP-ENG-003", 29, "789 Mission St, San Francisco, CA", "Engineering", "Senior Full Stack Engineer", "+1 (555) 010-003", "San Francisco Branch", "2022-01-10", 2),
            (4, 4, "EMP-ENG-004", 27, "321 Congress Ave, Austin, TX", "Engineering", "Frontend UI/UX Engineer", "+1 (555) 010-004", "Austin Branch", "2022-04-18", 2),
            (5, 5, "EMP-ENG-005", 31, "654 Michigan Ave, Chicago, IL", "Engineering", "Backend Database Engineer", "+1 (555) 010-005", "Remote - Chicago", "2023-02-01", 2)
        ]
        cursor.executemany(
            "INSERT INTO employees (employee_id, user_id, employee_code, age, address, department, designation, phone, location, joining_date, manager_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            emp_data
        )

        # 3. Projects
        projects_data = [
            (1, 3, "NextGen Enterprise Appraisal Portal", "Platform Engineering", "End-to-end multi-role appraisal system with automated reviews and audit trails.", 80, "in_progress", "High", "2026-12-15", 4, 5),
            (2, 3, "Zero-Downtime Microservice Migration", "Infrastructure", "Migrate legacy monolith services to isolated stateless backend services.", 100, "completed", "Critical", "2026-07-20", 6, 6),
            (3, 4, "Unified Corporate Design System", "UI/UX Design", "Modern accessible responsive component kit for all internal web tools.", 75, "in_progress", "High", "2026-10-30", 3, 4),
            (4, 5, "High-Availability Database Cluster", "Infrastructure", "Configure primary-replica replication with automated failover and backups.", 60, "in_progress", "High", "2026-11-20", 3, 5)
        ]
        cursor.executemany(
            "INSERT INTO projects (project_id, employee_id, name, category, description, progress, status, priority, due_date, milestones_completed, milestones_total) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            projects_data
        )

        # 4. Appraisals
        appraisals_data = [
            (1, 3, 2, "FY2025-Q4", 4.50, 4.70, "Exceeded delivery targets on architecture modernization and security audits.", "Outstanding technical leadership and high reliability across projects.", "APPROVED"),
            (2, 3, 2, "FY2026-Q1", None, 4.60, "Completed core delivery milestones early. Mentored junior developers.", None, "UNDER_REVIEW"),
            (3, 4, 2, "FY2026-Q1", 4.20, 4.30, "Standardized design tokens and eliminated frontend layout drift.", "Consistently high visual quality and team collaboration.", "APPROVED"),
            (4, 5, 2, "FY2026-Q1", 3.20, 4.00, "Maintained 99.9% database uptime during migration window.", "Good delivery, but incident post-mortem documentation was delayed.", "REJECTED")
        ]
        cursor.executemany(
            "INSERT INTO appraisals (appraisal_id, employee_id, manager_id, appraisal_period, overall_rating, self_rating, employee_comments, manager_comments, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            appraisals_data
        )

        # 5. Appeals
        cursor.execute(
            "INSERT INTO appeals (appeal_id, appraisal_id, employee_id, reason, status) VALUES (%s, %s, %s, %s, %s)",
            (1, 4, 5, "The incident post-mortems were delayed due to urgent unannounced hardware failures beyond team control.", "pending")
        )

        # 6. Investigations
        cursor.execute(
            "INSERT INTO investigations (investigation_id, employee_id, manager_id, higher_authority_id, appraisal_id, issue_type, subject, description, evidence_details, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (1, 3, 2, 1, 1, "Policy Clarification", "Clarification on Remote Equipment Allowance Policy", "Requesting guidance regarding multi-monitor home workstation reimbursement.", "Attached receipts submitted on corporate expense portal ticket #4092.", "pending")
        )

        # 7. Documents
        doc_data = [
            (1, 3, "Annual Performance Summary", "Q4_Architecture_Deliverables.pdf", "static/uploads/documents/sample_summary.pdf", "approved", "Verified and thoroughly documented deliverables."),
            (2, 3, "Technical Certification", "AWS_Solutions_Architect_Certificate.pdf", "static/uploads/documents/sample_cert.pdf", "pending", None)
        ]
        cursor.executemany(
            "INSERT INTO documents (document_id, employee_id, document_type, document_name, document_path, status, manager_comments) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            doc_data
        )

        # 8. Document Verification
        cursor.execute(
            "INSERT INTO document_verification (verification_id, document_id, manager_id, action, comments) VALUES (%s, %s, %s, %s, %s)",
            (1, 1, 2, "approved", "All deliverables match repository commit logs and sprint metrics.")
        )

        # 9. Audit Logs
        audit_data = [
            (1, "SYSTEM_INIT", "DATABASE", 1, "Initial database schema and system configuration loaded."),
            (2, "REVIEW_APPRAISAL", "APPRAISAL", 1, "Manager Alex Rivera approved appraisal for David Chen (FY2025-Q4)."),
            (3, "SUBMIT_APPRAISAL", "APPRAISAL", 2, "David Chen submitted self-appraisal for FY2026-Q1."),
            (5, "SUBMIT_APPEAL", "APPEAL", 1, "Michael Brown submitted appeal for appraisal #4.")
        ]
        cursor.executemany(
            "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description) VALUES (%s, %s, %s, %s, %s)",
            audit_data
        )

        conn.commit()
        print("[DATABASE] Development dataset seeded successfully.")
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DATABASE ERROR] Seeding failed: {e}")
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# PASSWORD ENFORCEMENT & OTP 2FA
# ============================================================

def force_update_user_password(user_id, new_password_hash):
    """
    Force update user's password (e.g. on first login after promotion).
    Clears the must_change_password flag and logs the event.
    """
    sql = "UPDATE users SET password_hash = %s, must_change_password = 0 WHERE user_id = %s"
    result = execute_query(sql, (new_password_hash, user_id), commit=True)
    create_audit_log(user_id, "FORCE_CHANGE_PASSWORD", "USER", user_id, "User updated temporary password.")
    return result


def set_must_change_password(user_id, flag=1):
    """Set or clear must_change_password flag for a user."""
    sql = "UPDATE users SET must_change_password = %s WHERE user_id = %s"
    return execute_query(sql, (flag, user_id), commit=True)


def set_email_verified(user_id):
    """Mark a user's email as verified after successful registration OTP. Call only once during signup."""
    sql = "UPDATE users SET email_verified = 1 WHERE user_id = %s"
    result = execute_query(sql, (user_id,), commit=True)
    create_audit_log(user_id, "EMAIL_VERIFIED", "USER", user_id, "User verified email via registration OTP.")
    return result


def hash_otp(otp_code: str) -> str:
    """Compute SHA-256 hash of OTP code for secure storage."""
    return hashlib.sha256(otp_code.strip().encode("utf-8")).hexdigest()


def create_otp(user_id, otp_code, expiry_seconds=120):
    """
    Store hashed OTP code with 2-minute expiration for 2FA login.
    """
    otp_hashed = hash_otp(otp_code)
    expires_at = datetime.now() + timedelta(seconds=expiry_seconds)
    sql = """
        INSERT INTO login_otps (user_id, otp_hash, expires_at, attempts)
        VALUES (%s, %s, %s, 0)
    """
    return execute_query(sql, (user_id, otp_hashed, expires_at), commit=True, return_lastrowid=True)


def get_active_otp_for_user(user_id):
    """Retrieve the latest unverified and non-expired OTP record for a user."""
    sql = """
        SELECT * FROM login_otps
        WHERE user_id = %s AND verified_at IS NULL AND expires_at > NOW()
        ORDER BY created_at DESC
        LIMIT 1
    """
    return execute_query(sql, (user_id,), fetchone=True)


def verify_user_otp(user_id, otp_entered):
    """
    Verify entered OTP against active hashed OTP in database.
    Returns (success: bool, message: str).
    """
    active_otp = get_active_otp_for_user(user_id)
    if not active_otp:
        return False, "No active or valid OTP found. Please log in again to receive a new code."

    # Enforce maximum attempt limit (5 attempts)
    if active_otp.get("attempts", 0) >= 5:
        return False, "Maximum verification attempts exceeded. Please log in again to generate a new OTP."

    # Increment attempts
    otp_id = active_otp["otp_id"]
    execute_query("UPDATE login_otps SET attempts = attempts + 1 WHERE otp_id = %s", (otp_id,), commit=True)

    # Check hash match
    input_hash = hash_otp(otp_entered)
    if input_hash == active_otp["otp_hash"]:
        execute_query("UPDATE login_otps SET verified_at = NOW() WHERE otp_id = %s", (otp_id,), commit=True)
        create_audit_log(user_id, "OTP_VERIFIED", "USER", user_id, "User successfully completed 2FA OTP verification.")
        return True, "OTP verified successfully."
    else:
        return False, "Invalid verification code. Please check and try again."


# ============================================================
# CLAIMS SYSTEM (EMPLOYEES CLAIM ADDITIONAL WORK)
# ============================================================

def create_claim(employee_id, appraisal_period, title, description, work_date=None, document_reference=None):
    """Create a new work claim submitted by an employee."""
    sql = """
        INSERT INTO claims (employee_id, appraisal_period, title, description, work_date, document_reference, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'SUBMITTED')
    """
    claim_id = execute_query(
        sql,
        (employee_id, appraisal_period, title, description, work_date, document_reference),
        commit=True,
        return_lastrowid=True
    )
    # Get user_id for audit logging
    emp = get_employee_by_id(employee_id)
    if emp and emp.get("user_id"):
        create_audit_log(emp["user_id"], "SUBMIT_CLAIM", "CLAIM", claim_id, f"Employee submitted claim: {title}")
    return claim_id


def get_claims_by_employee(employee_id):
    """Retrieve all claims submitted by an employee with review info."""
    sql = """
        SELECT c.*, u.name as manager_name, u.email as manager_email
        FROM claims c
        LEFT JOIN users u ON c.manager_id = u.user_id
        WHERE c.employee_id = %s
        ORDER BY c.created_at DESC
    """
    return execute_query(sql, (employee_id,), fetchall=True)


def get_claims_for_manager(manager_user_id):
    """Retrieve all claims submitted by employees reporting to this manager."""
    sql = """
        SELECT c.*, e.employee_code, e.department, e.designation,
               u.name as employee_name, u.email as employee_email
        FROM claims c
        JOIN employees e ON c.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        WHERE e.manager_id = %s
        ORDER BY c.created_at DESC
    """
    return execute_query(sql, (manager_user_id,), fetchall=True)


def get_claim_by_id(claim_id):
    """Retrieve claim details with employee and manager info."""
    sql = """
        SELECT c.*, e.employee_code, e.department, e.designation, e.manager_id as assigned_manager_id,
               u.name as employee_name, u.email as employee_email,
               m.name as manager_name
        FROM claims c
        JOIN employees e ON c.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON c.manager_id = m.user_id
        WHERE c.claim_id = %s
    """
    return execute_query(sql, (claim_id,), fetchone=True)


def review_claim(claim_id, manager_id, status, manager_comments=None):
    """Approve or reject an employee claim with manager comments."""
    if status not in ("APPROVED", "REJECTED"):
        raise ValueError("Invalid claim status. Must be APPROVED or REJECTED.")
    sql = """
        UPDATE claims
        SET status = %s, manager_id = %s, manager_comments = %s, reviewed_at = NOW()
        WHERE claim_id = %s
    """
    result = execute_query(sql, (status, manager_id, manager_comments, claim_id), commit=True)
    create_audit_log(manager_id, "REVIEW_CLAIM", "CLAIM", claim_id, f"Manager reviewed claim #{claim_id} with status {status}")
    return result


# ============================================================
# PROJECT TASKS & TASK REVIEWS
# ============================================================

def create_project_task(project_id, employee_id, assigned_by, title, description=None, due_date=None):
    """Assign an individual project task to an employee."""
    sql = """
        INSERT INTO project_tasks (project_id, employee_id, assigned_by, title, description, due_date, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
    """
    task_id = execute_query(
        sql,
        (project_id, employee_id, assigned_by, title, description, due_date),
        commit=True,
        return_lastrowid=True
    )
    create_audit_log(assigned_by, "ASSIGN_TASK", "PROJECT_TASK", task_id, f"Assigned task '{title}' to employee #{employee_id}")
    return task_id


def get_tasks_by_employee(employee_id):
    """Retrieve all tasks assigned to an employee with review ratings."""
    sql = """
        SELECT pt.*, p.name AS project_name, u.name AS assigned_by_name,
               tr.review_id, tr.rating AS manager_rating,
               tr.comments AS manager_comments, tr.reviewed_at
        FROM project_tasks pt
        JOIN projects p ON pt.project_id = p.project_id
        JOIN users u ON pt.assigned_by = u.user_id
        LEFT JOIN task_reviews tr ON pt.task_id = tr.task_id
        WHERE pt.employee_id = %s
        ORDER BY pt.created_at DESC
    """
    return execute_query(sql, (employee_id,), fetchall=True)


def get_tasks_by_manager(manager_user_id):
    """Retrieve tasks assigned by manager or for employees reporting to manager."""
    sql = """
        SELECT pt.*, p.name AS project_name, e.employee_code, e.department,
               u.name as employee_name, u.email as employee_email,
               tr.review_id, tr.rating AS manager_rating,
               tr.comments AS manager_comments, tr.reviewed_at
        FROM project_tasks pt
        JOIN projects p ON pt.project_id = p.project_id
        JOIN employees e ON pt.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN task_reviews tr ON pt.task_id = tr.task_id
        WHERE pt.assigned_by = %s OR e.manager_id = %s
        ORDER BY pt.created_at DESC
    """
    return execute_query(sql, (manager_user_id, manager_user_id), fetchall=True)


def get_task_by_id(task_id):
    """Retrieve task details by ID with project, employee, and review info."""
    sql = """
        SELECT pt.*, p.name AS project_name, e.employee_code, e.employee_id, e.manager_id,
               u.name as employee_name, u.email as employee_email,
               ab.name as assigned_by_name,
               tr.review_id, tr.rating AS manager_rating,
               tr.comments AS manager_comments, tr.reviewed_at
        FROM project_tasks pt
        JOIN projects p ON pt.project_id = p.project_id
        JOIN employees e ON pt.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        JOIN users ab ON pt.assigned_by = ab.user_id
        LEFT JOIN task_reviews tr ON pt.task_id = tr.task_id
        WHERE pt.task_id = %s
    """
    return execute_query(sql, (task_id,), fetchone=True)


def submit_task_result(task_id, employee_id, status, employee_result=None, employee_reason=None):
    """Employee updates the status and submits deliverables/results for an assigned task."""
    sql = """
        UPDATE project_tasks
        SET status = %s, employee_result = %s, employee_reason = %s, submitted_at = NOW()
        WHERE task_id = %s AND employee_id = %s
    """
    result = execute_query(sql, (status, employee_result, employee_reason, task_id, employee_id), commit=True)
    emp = get_employee_by_id(employee_id)
    user_id = emp["user_id"] if emp else None
    if user_id:
        create_audit_log(user_id, "SUBMIT_TASK_RESULT", "PROJECT_TASK", task_id, f"Employee submitted result for task #{task_id}")
    return result


def review_task(task_id, manager_id, rating, comments=None):
    """
    Manager reviews a completed project task and assigns a rating from 1.00 to 5.00.
    """
    rating = float(rating)
    if rating < 1.00 or rating > 5.00:
        raise ValueError("Task rating must be between 1.00 and 5.00.")

    sql = """
        INSERT INTO task_reviews (task_id, manager_id, rating, comments, reviewed_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            manager_id = VALUES(manager_id),
            rating = VALUES(rating),
            comments = VALUES(comments),
            reviewed_at = NOW()
    """
    result = execute_query(sql, (task_id, manager_id, rating, comments), commit=True)
    create_audit_log(manager_id, "REVIEW_TASK", "TASK_REVIEW", task_id, f"Manager rated task #{task_id} with {rating:.2f}/5.00")
    return result


def calculate_task_average(employee_id):
    """
    Server-side calculation of an employee's average rating across all reviewed tasks.
    Returns (task_average: float, total_reviews: int).
    """
    sql = """
        SELECT AVG(tr.rating) as avg_rating, COUNT(tr.review_id) as total_reviews
        FROM task_reviews tr
        JOIN project_tasks pt ON tr.task_id = pt.task_id
        WHERE pt.employee_id = %s
    """
    row = execute_query(sql, (employee_id,), fetchone=True)
    if not row or row.get("avg_rating") is None:
        return 0.0, 0
    return round(float(row["avg_rating"]), 2), int(row.get("total_reviews", 0))


def check_promotion_eligibility(employee_id):
    """
    Determines if an employee is eligible for promotion based on task average.
    Requirement: task average must be strictly GREATER THAN 4.60.
    """
    avg_rating, total_reviews = calculate_task_average(employee_id)
    threshold = getattr(Config, "PROMOTION_ELIGIBILITY_THRESHOLD", 4.60)
    eligible = (avg_rating > threshold) and (total_reviews > 0)
    return {
        "eligible": eligible,
        "task_average": avg_rating,
        "total_reviews": total_reviews,
        "threshold": threshold,
        "message": "Eligible for promotion." if eligible else f"Performance average ({avg_rating:.2f}) must be strictly greater than {threshold:.2f}."
    }


# ============================================================
# PROMOTION REQUESTS & HR APPROVAL WORKFLOW
# ============================================================

def create_promotion_request(employee_id, appraisal_id=None, manager_id=None, reason="", document_reference=None, task_average=None):
    """
    Employee creates a formal promotion request.
    Server computes the authoritative task average to store alongside the request.
    """
    # Authoritatively compute server-side task average
    computed_avg, _ = calculate_task_average(employee_id)
    avg_to_store = computed_avg if computed_avg > 0 else task_average

    sql = """
        INSERT INTO promotion_requests (employee_id, appraisal_id, manager_id, reason, document_reference, status, task_average)
        VALUES (%s, %s, %s, %s, %s, 'SUBMITTED', %s)
    """
    request_id = execute_query(
        sql,
        (employee_id, appraisal_id, manager_id, reason, document_reference, avg_to_store),
        commit=True,
        return_lastrowid=True
    )
    emp = get_employee_by_id(employee_id)
    if emp and emp.get("user_id"):
        create_audit_log(emp["user_id"], "SUBMIT_PROMOTION_REQUEST", "PROMOTION_REQUEST", request_id, f"Employee submitted promotion request #{request_id}")
    return request_id


def get_promotion_requests_for_hr(status=None):
    """Retrieve all promotion requests with employee and manager details for HR."""
    params = []
    where_clause = ""
    if status:
        where_clause = "WHERE pr.status = %s"
        params.append(status)

    sql = f"""
        SELECT pr.*, e.employee_code, e.department, e.designation as current_designation,
               u.name as employee_name, u.email as employee_email, u.user_id as employee_user_id,
               m.name as manager_name,
               h.name as hr_name
        FROM promotion_requests pr
        JOIN employees e ON pr.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON pr.manager_id = m.user_id
        LEFT JOIN users h ON pr.hr_id = h.user_id
        {where_clause}
        ORDER BY pr.created_at DESC
    """
    return execute_query(sql, tuple(params) if params else None, fetchall=True)


def get_promotion_request_by_id(request_id):
    """Retrieve detailed promotion request by ID."""
    sql = """
        SELECT pr.*, e.employee_code, e.department, e.designation as current_designation,
               u.name as employee_name, u.email as employee_email, u.user_id as employee_user_id,
               m.name as manager_name,
               h.name as hr_name
        FROM promotion_requests pr
        JOIN employees e ON pr.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON pr.manager_id = m.user_id
        LEFT JOIN users h ON pr.hr_id = h.user_id
        WHERE pr.request_id = %s
    """
    return execute_query(sql, (request_id,), fetchone=True)


def reject_promotion_request(request_id, hr_user_id, hr_response=None):
    """HR rejects an employee promotion request with comments."""
    sql = """
        UPDATE promotion_requests
        SET status = 'REJECTED', hr_id = %s, hr_response = %s
        WHERE request_id = %s
    """
    result = execute_query(sql, (hr_user_id, hr_response, request_id), commit=True)
    create_audit_log(hr_user_id, "REJECT_PROMOTION", "PROMOTION_REQUEST", request_id, f"HR rejected promotion request #{request_id}")
    return result


def approve_promotion_transaction(request_id, hr_user_id, temp_password_hash, hr_response=None, new_designation=None):
    """
    Executes a multi-step database transaction for approving a promotion:
    1. Validates promotion request status is SUBMITTED or UNDER_REVIEW
    2. Verifies employee's current user account has role 'employee'
    3. Upgrades user.role to 'manager'
    4. Sets temporary password hash and must_change_password = 1 on users table
    5. Updates employee.designation to new designation (or 'Manager')
    6. Creates permanent record in promotions table
    7. Marks promotion_requests status as APPROVED
    8. Records audit log entry
    Returns a dictionary of promotion details for email notification, or raises Exception on failure.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Fetch promotion request
        cursor.execute("SELECT * FROM promotion_requests WHERE request_id = %s", (request_id,))
        req = cursor.fetchone()
        if not req:
            raise ValueError(f"Promotion request #{request_id} not found.")
        if req["status"] not in ("SUBMITTED", "UNDER_REVIEW"):
            raise ValueError(f"Promotion request is already in '{req['status']}' state.")

        employee_id = req["employee_id"]

        # 2. Fetch employee and user info
        cursor.execute("""
            SELECT e.*, u.user_id, u.name, u.email, u.role as current_role
            FROM employees e
            JOIN users u ON e.user_id = u.user_id
            WHERE e.employee_id = %s
        """, (employee_id,))
        emp_user = cursor.fetchone()
        if not emp_user:
            raise ValueError(f"Employee record #{employee_id} not found.")

        user_id = emp_user["user_id"]
        previous_role = emp_user["current_role"]
        previous_designation = emp_user.get("designation") or "Associate"
        target_designation = new_designation or "Manager"
        target_role = "manager"
        task_avg = req.get("task_average") or 0.0

        # 3. Upgrade user role and set temp password + must_change_password
        cursor.execute("""
            UPDATE users
            SET role = %s, password_hash = %s, must_change_password = 1
            WHERE user_id = %s
        """, (target_role, temp_password_hash, user_id))

        # 4. Update employee designation
        cursor.execute("""
            UPDATE employees
            SET designation = %s
            WHERE employee_id = %s
        """, (target_designation, employee_id))

        # 5. Insert permanent promotion history record
        cursor.execute("""
            INSERT INTO promotions (
                employee_id, promotion_request_id, appraisal_id,
                previous_role, new_role, previous_designation, new_designation,
                approved_by, task_average, effective_date, comments
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURDATE(), %s)
        """, (
            employee_id, request_id, req.get("appraisal_id"),
            previous_role, target_role, previous_designation, target_designation,
            hr_user_id, task_avg, hr_response
        ))

        # 6. Mark promotion request APPROVED
        cursor.execute("""
            UPDATE promotion_requests
            SET status = 'APPROVED', hr_id = %s, hr_response = %s
            WHERE request_id = %s
        """, (hr_user_id, hr_response, request_id))

        # 7. Audit log
        cursor.execute("""
            INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            hr_user_id, "APPROVE_PROMOTION", "PROMOTION", request_id,
            f"HR approved promotion for {emp_user['name']} to {target_role} ({target_designation})."
        ))

        conn.commit()

        return {
            "success": True,
            "employee_id": employee_id,
            "user_id": user_id,
            "name": emp_user["name"],
            "email": emp_user["email"],
            "previous_role": previous_role,
            "new_role": target_role,
            "previous_designation": previous_designation,
            "new_designation": target_designation,
            "task_average": float(task_avg) if task_avg else 0.0
        }
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_promotions_history(employee_id=None):
    """Retrieve permanent record of completed promotions with employee and approver details."""
    params = []
    where_clause = ""
    if employee_id:
        where_clause = "WHERE p.employee_id = %s"
        params.append(employee_id)

    sql = f"""
        SELECT p.*, e.employee_code, u.name as employee_name, u.email as employee_email,
               a.name as approver_name
        FROM promotions p
        JOIN employees e ON p.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        JOIN users a ON p.approved_by = a.user_id
        {where_clause}
        ORDER BY p.created_at DESC
    """
    return execute_query(sql, tuple(params) if params else None, fetchall=True)


# ============================================================
# ADMINISTRATOR ROLE OPERATIONS
# ============================================================

def get_all_employees_admin():
    """Retrieve all employee records with associated users and managers for administrator portal."""
    sql = """
        SELECT e.*, u.name, u.email, u.role, u.must_change_password,
               m.name as manager_name, m.email as manager_email
        FROM users u
        LEFT JOIN employees e ON u.user_id = e.user_id
        LEFT JOIN users m ON e.manager_id = m.user_id
        ORDER BY u.user_id ASC
    """
    return execute_query(sql, fetchall=True)


def get_all_projects_admin():
    """Retrieve all projects with manager/employee details and task statistics for administrator portal."""
    sql = """
        SELECT p.*, 
               e.employee_code,
               u.name as employee_name, u.email as employee_email,
               m.name as manager_name
        FROM projects p
        JOIN employees e ON p.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON e.manager_id = m.user_id
        ORDER BY p.created_at DESC
    """
    return execute_query(sql, fetchall=True)


def create_project_admin(name, employee_id, category=None, description=None, priority='Medium', due_date=None, milestones_total=1):
    """Administrator creates and assigns a project to an employee."""
    sql = """
        INSERT INTO projects (name, employee_id, category, description, priority, due_date, milestones_total, progress, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'pending')
    """
    proj_id = execute_query(sql, (name, employee_id, category, description, priority, due_date, milestones_total), commit=True, return_lastrowid=True)
    create_audit_log(None, "ADMIN_CREATE_PROJECT", "PROJECT", proj_id, f"Administrator created and assigned project '{name}' to employee #{employee_id}")
    return proj_id


def get_all_tasks_admin():
    """Retrieve all project tasks across the organization for administrator overview."""
    sql = """
        SELECT pt.*, p.name as project_name, 
               e.employee_code, e.department,
               u.name as employee_name, u.email as employee_email,
               ab.name as assigned_by_name,
               tr.rating AS manager_rating,
               tr.comments AS manager_comments, tr.reviewed_at
        FROM project_tasks pt
        JOIN projects p ON pt.project_id = p.project_id
        JOIN employees e ON pt.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        JOIN users ab ON pt.assigned_by = ab.user_id
        LEFT JOIN task_reviews tr ON pt.task_id = tr.task_id
        ORDER BY pt.created_at DESC
    """
    return execute_query(sql, fetchall=True)


def get_all_claims_admin():
    """Retrieve all additional work claims submitted by employees."""
    sql = """
        SELECT c.*, e.employee_code, e.department,
               u.name as employee_name, u.email as employee_email,
               m.name as manager_name
        FROM claims c
        JOIN employees e ON c.employee_id = e.employee_id
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN users m ON c.manager_id = m.user_id
        ORDER BY c.created_at DESC
    """
    return execute_query(sql, fetchall=True)


def get_admin_dashboard_metrics():
    """Retrieve high-level system metrics for administrator overview."""
    total_users = execute_query("SELECT COUNT(*) as cnt FROM users", fetchone=True).get("cnt", 0)
    total_employees = execute_query("SELECT COUNT(*) as cnt FROM employees", fetchone=True).get("cnt", 0)
    total_projects = execute_query("SELECT COUNT(*) as cnt FROM projects", fetchone=True).get("cnt", 0)
    total_tasks = execute_query("SELECT COUNT(*) as cnt FROM project_tasks", fetchone=True).get("cnt", 0)
    completed_tasks = execute_query("SELECT COUNT(*) as cnt FROM project_tasks WHERE status = 'COMPLETED'", fetchone=True).get("cnt", 0)
    pending_promotions = execute_query("SELECT COUNT(*) as cnt FROM promotion_requests WHERE status = 'SUBMITTED'", fetchone=True).get("cnt", 0)
    open_investigations = execute_query("SELECT COUNT(*) as cnt FROM investigations WHERE status = 'pending'", fetchone=True).get("cnt", 0)
    total_claims = execute_query("SELECT COUNT(*) as cnt FROM claims", fetchone=True).get("cnt", 0)

    return {
        "total_users": total_users,
        "total_employees": total_employees,
        "total_projects": total_projects,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_promotions": pending_promotions,
        "open_investigations": open_investigations,
        "total_claims": total_claims
    }
