# Employee Appraisal Management System (EAMS)

A clean, reliable, multi-role Employee Appraisal Management System built with Python, Flask, Jinja2, Vanilla CSS/JavaScript, and MySQL 8+.

---

## 1. Project Overview

The **Employee Appraisal Management System (EAMS)** streamlines the corporate performance review lifecycle. It features strict role-based access control across three user roles (**Employee**, **Manager**, and **HR**), ensuring secure self-assessments, manager evaluations, performance document verification, appeals, and escalated HR investigations with an immutable append-only audit trail.

---

## 2. Architecture & Business Workflow

```
Employee
    ↓
Submits self-appraisal
    ↓
Status = UNDER_REVIEW
    ↓
Manager reviews appraisal
    ↓
APPROVED / REJECTED / CHANGES_REQUESTED
    ↓
Employee sees result & manager comments
    ↓
If employee disagrees
    ↓
Employee submits appeal
    ↓
Manager reviews appeal
    ↓
Manager approves/reconsiders OR rejects appeal
    ↓
If employee believes manager is behaving unfairly
    ↓
Employee submits complaint/escalation to HR
    ↓
HR reviews/investigates complaint
    ↓
HR records official ruling (UNDER_INVESTIGATION, RESOLVED_UPHELD, RESOLVED_REJECTED)
    ↓
Employee sees final HR result
```

All states, ratings, comments, and actions are saved permanently in MySQL.

---

## 3. Technology Stack & Requirements

- **Python**: 3.9+
- **Database**: MySQL 8.0+ or MariaDB 10.5+
- **Packages**:
  - `Flask>=3.0.0`
  - `mysql-connector-python>=8.3.0`
  - `python-dotenv>=1.0.0`
  - `Werkzeug>=3.0.0`

---

## 4. Application Structure

### Public
- `/`: Sign In Portal (with quick demo credentials)
- `/register`: Employee Registration (with real-time password strength indicator)

### Employee Portal
- `/employee/dashboard`: Workspace summary metrics and recent activity
- `/employee/profile`: View & edit profile details (age, address, phone, location) + Change password
- `/employee/documents`: Upload and manage performance verification documents
- `/employee/appraisal`: Submit self-appraisal (`UNDER_REVIEW`) and review manager ratings
- `/employee/appeals`: File and track appraisal appeals / reconsideration requests
- `/employee/investigations`: File complaints/escalations to HR and view official HR rulings
- `/employee/projects`: Project deliverables and milestone tracking

### Manager Portal
- `/manager/dashboard`: Direct reports overview and pending review counts
- `/manager/profile`: View & edit profile details + Change password
- `/manager/documents`: Verify and review submitted employee documents
- `/manager/appraisals`: Review direct report appraisals (`APPROVED`, `REJECTED`, `CHANGES_REQUESTED`)
- `/manager/appeals`: Review employee appeals with official manager responses
- `/manager/team`: Team directory and direct reports roster
- `/manager/projects`: Team projects delivery and milestone updates

### HR Administration Portal
- `/hr/dashboard`: Organization-wide metrics and pending complaints overview
- `/hr/profile`: View & edit profile details + Change password
- `/hr/employees`: Employee directory, department filtering, and employee account creation
- `/hr/investigations`: Review escalated grievances and record official HR rulings
- `/hr/appraisals`: Organization-wide appraisal review calibration
- `/hr/reports`: Analytics, completion rates, department ratings, and rating distributions
- `/hr/audit-logs`: Append-only tamper-evident audit trail
- `/hr/projects`: Strategic organizational deliverables

---

## 5. Setup & Running Locally

1. **Configure Environment Variables** in `.env`:
   ```env
   FLASK_SECRET_KEY=your-secure-secret-key
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=employee_appraisal
   ```

2. **Initialize Database** (MySQL):
   ```bash
   mysql -u root -p < sql/schema.sql
   mysql -u root -p employee_appraisal < sql/seed.sql
   ```

3. **Install Dependencies & Start Application**:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```

4. **Default Demo Accounts** (Password for all: `Password@123`):
   - **HR Director**: `hr@example.com`
   - **Engineering Manager**: `manager@example.com`
   - **Senior Engineer**: `employee@example.com`
   - **Frontend Engineer**: `emily.watson@example.com`
   - **Database Engineer**: `michael.brown@example.com`
