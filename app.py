"""
Employee Appraisal Management System (EAMS)
Main Flask Application
"""

import os
import re
import secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
import database as db
import email_service

# Initialize Flask App
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    """Helper function to check allowed file extensions."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def validate_password_strength(password):
    """
    Validates minimum password requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit or special character
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"[0-9\W_]", password):
        return False, "Password must contain at least one number or special character."
    return True, "Password meets requirements."



# ROLE & AUTH DECORATORS


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Authentication required"}), 401
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("login"))

        # Server-side enforcement of password change on first login after promotion
        if session.get("must_change_password"):
            allowed_endpoints = ("force_password_change", "logout", "static")
            if request.endpoint not in allowed_endpoints and not request.path.startswith("/api/force-password-change"):
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "must_change_password": True, "message": "Temporary password detected. Password change required before proceeding."}), 403
                flash("You must update your temporary password before accessing the system.", "warning")
                return redirect(url_for("force_password_change"))

        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "message": "Authentication required"}), 401
                return redirect(url_for("login"))
            
            user_role = session.get("role", "").lower()
            if user_role == "admin":
                user_role = "hr"

            normalized_allowed = [r.lower() for r in allowed_roles]
            if user_role not in normalized_allowed:
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "message": "Access denied: insufficient privileges"}), 403
                flash("You are not authorized to view this resource.", "danger")
                if user_role == "employee":
                    return redirect(url_for("employee_dashboard"))
                elif user_role == "manager":
                    return redirect(url_for("manager_dashboard"))
                elif user_role in ("hr", "admin"):
                    return redirect(url_for("hr_dashboard"))
                elif user_role == "administrator":
                    return redirect(url_for("administrator_dashboard"))
                return redirect(url_for("login"))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator



# AUTHENTICATION & REGISTRATION ROUTES


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html")

        user = db.get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email address or password.", "danger")
            return render_template("login.html")

        # Directly authenticate user without OTP
        session.clear()
        session["user_id"] = user["user_id"]
        session["name"] = user["name"]
        session["email"] = user["email"]
        session["role"] = user["role"].lower()
        session["must_change_password"] = bool(user.get("must_change_password"))
        session["user"] = {
            "id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"].lower(),
            "must_change_password": bool(user.get("must_change_password"))
        }

        # Write audit log
        db.create_audit_log(user["user_id"], "LOGIN", "USER", user["user_id"], f"User {user['email']} logged in.")

        # Check if must change temporary password
        if session.get("must_change_password"):
            flash("Temporary credentials detected. Please set your new permanent password.", "warning")
            return redirect(url_for("force_password_change"))

        flash("Welcome back!", "success")

        # Route to role dashboard
        role = user["role"].lower()
        if role == "employee":
            return redirect(url_for("employee_dashboard"))
        elif role == "manager":
            return redirect(url_for("manager_dashboard"))
        elif role in ("hr", "admin"):
            return redirect(url_for("hr_dashboard"))
        elif role == "administrator":
            return redirect(url_for("administrator_dashboard"))
        else:
            return redirect(url_for("employee_dashboard"))

    # If already fully logged in, route to appropriate dashboard
    if "user_id" in session:
        role = session.get("role")
        if role == "employee":
            return redirect(url_for("employee_dashboard"))
        elif role == "manager":
            return redirect(url_for("manager_dashboard"))
        elif role in ("hr", "admin"):
            return redirect(url_for("hr_dashboard"))
        elif role == "administrator":
            return redirect(url_for("administrator_dashboard"))

    return render_template("login.html")


@app.route("/otp-verify", methods=["GET", "POST"])
def otp_verify():
    return redirect(url_for("login"))


@app.route("/resend-otp", methods=["GET"])
def resend_otp():
    return redirect(url_for("login"))


@app.route("/force-password-change", methods=["GET", "POST"])
def force_password_change():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if not session.get("must_change_password"):
        role = session.get("role", "employee")
        if role == "manager":
            return redirect(url_for("manager_dashboard"))
        elif role in ("hr", "admin"):
            return redirect(url_for("hr_dashboard"))
        elif role == "administrator":
            return redirect(url_for("administrator_dashboard"))
        return redirect(url_for("employee_dashboard"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not new_password or not confirm_password:
            flash("Please fill in both password fields.", "danger")
            return render_template("force_password_change.html")

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return render_template("force_password_change.html")

        is_valid, msg = validate_password_strength(new_password)
        if not is_valid:
            flash(f"Password does not meet the minimum requirements: {msg}", "danger")
            return render_template("force_password_change.html")

        new_hash = generate_password_hash(new_password)
        db.force_update_user_password(session["user_id"], new_hash)
        session["must_change_password"] = False
        if "user" in session:
            session["user"]["must_change_password"] = False

        flash("Your password has been successfully updated! Welcome to your new role.", "success")
        role = session.get("role", "employee")
        if role == "manager":
            return redirect(url_for("manager_dashboard"))
        elif role in ("hr", "admin"):
            return redirect(url_for("hr_dashboard"))
        elif role == "administrator":
            return redirect(url_for("administrator_dashboard"))
        return redirect(url_for("employee_dashboard"))

    return render_template("force_password_change.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        age = request.form.get("age", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "Engineering").strip()
        location = request.form.get("location", "").strip()
        role = request.form.get("role", "employee").strip().lower()

        # Public sign-up is intentionally limited to operational user roles.
        # HR/administrator accounts are provisioned by the system, never from this form.
        if role not in ("employee", "manager"):
            flash("Please select either Employee or Manager as the account role.", "danger")
            return render_template("register.html")

        # Required fields validation
        if not name or not email or not password or not confirm_password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")

        # Gmail-only registration policy for new users
        if not email.endswith("@gmail.com"):
            flash("Registration is restricted to official Gmail accounts (@gmail.com).", "danger")
            return render_template("register.html")

        # Password matching
        if password != confirm_password:
            flash("New passwords do not match.", "danger")
            return render_template("register.html")

        # Password strength
        is_valid, msg = validate_password_strength(password)
        if not is_valid:
            flash(f"Password does not meet the minimum requirements: {msg}", "danger")
            return render_template("register.html")

        # Check existing user
        if db.get_user_by_email(email):
            flash("Email already registered. Please sign in or use a different email.", "danger")
            return render_template("register.html")

        # Age parsing & validation: must be at least 21
        age_val = None
        if not age:
            flash("Age is required. Employees must be at least 21 years of age.", "danger")
            return render_template("register.html")
        try:
            age_val = int(age)
            if age_val < 21:
                flash("Registration rejected: Employees must be at least 21 years of age.", "danger")
                return render_template("register.html")
        except ValueError:
            flash("Please enter a valid numeric age.", "danger")
            return render_template("register.html")

        # Hash password and create the user and matching employee/profile record.
        pwd_hash = generate_password_hash(password)
        try:
            result = db.create_employee_transaction(
                name=name,
                email=email,
                password_hash=pwd_hash,
                role=role,
                age=age_val,
                address=address,
                department=department or "Engineering",
                designation="Manager" if role == "manager" else "Software Engineer",
                phone=phone,
                location=location
            )
            action = "REGISTER_MANAGER" if role == "manager" else "REGISTER"
            db.create_audit_log(result["user_id"], action, "USER", result["user_id"], f"User {email} registered a new {role} account.")
            flash("Registration successful! Please sign in with your credentials.", "success")
            return redirect(url_for("login"))
        except Exception:
            flash("Registration could not be completed. Please try again.", "danger")
            return render_template("register.html")

    if "user_id" in session:
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        db.create_audit_log(user_id, "LOGOUT", "USER", user_id, "User signed out.")
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("login"))


# ============================================================
# UNIVERSAL PROFILE & PASSWORD ROUTES & APIS
# ============================================================

@app.route("/api/managers", methods=["GET"])
@login_required
def api_get_managers():
    """Return real manager accounts from MySQL for assignment forms."""
    return jsonify({"success": True, "data": db.get_users_by_roles(("manager",))}), 200


@app.route("/api/hr-users", methods=["GET"])
@login_required
def api_get_hr_users():
    """Return the existing HR authority (legacy admin role is supported)."""
    return jsonify({"success": True, "data": db.get_users_by_roles(("hr", "admin"))}), 200

@app.route("/employee/profile")
@login_required
@role_required("employee")
def employee_profile():
    emp = db.get_employee_by_user_id(session["user_id"])
    return render_template("employee/profile.html", active_page="profile", profile=emp)


@app.route("/manager/profile")
@login_required
@role_required("manager")
def manager_profile():
    emp = db.get_employee_by_user_id(session["user_id"])
    return render_template("manager/profile.html", active_page="profile", profile=emp)


@app.route("/hr/profile")
@login_required
@role_required("hr")
def hr_profile():
    emp = db.get_employee_by_user_id(session["user_id"])
    return render_template("hr/profile.html", active_page="profile", profile=emp)


@app.route("/api/profile", methods=["GET"])
@login_required
def api_get_profile():
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Profile not found"}), 404
    return jsonify({"success": True, "data": emp}), 200


@app.route("/api/profile/update", methods=["POST"])
@login_required
def api_update_profile():
    user_id = session["user_id"]
    data = request.get_json() or {}

    name = data.get("name", "").strip() if "name" in data else None
    age = data.get("age")
    address = data.get("address", "").strip() if "address" in data else None
    phone = data.get("phone", "").strip() if "phone" in data else None
    location = data.get("location", "").strip() if "location" in data else None
    department = data.get("department", "").strip() if "department" in data else None
    designation = data.get("designation", "").strip() if "designation" in data else None

    # Age validation if provided
    age_val = None
    if age is not None and str(age).strip() != "":
        try:
            age_val = int(age)
            if age_val < 16 or age_val > 100:
                return jsonify({"success": False, "message": "Please enter a valid age between 16 and 100"}), 422
        except ValueError:
            return jsonify({"success": False, "message": "Age must be a valid number"}), 422

    try:
        db.update_profile(
            user_id=user_id,
            name=name,
            age=age_val if age is not None else None,
            address=address,
            phone=phone,
            location=location,
            department=department,
            designation=designation
        )
        if name:
            session["name"] = name
            if "user" in session:
                session["user"]["name"] = name

        db.create_audit_log(user_id, "UPDATE_PROFILE", "USER", user_id, "User updated personal profile details.")
        return jsonify({"success": True, "message": "Profile updated successfully."}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to update profile: {str(e)}"}), 500


@app.route("/api/profile/change-password", methods=["POST"])
@login_required
def api_change_password():
    user_id = session["user_id"]
    data = request.get_json() or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not current_password or not new_password or not confirm_password:
        return jsonify({"success": False, "message": "Please fill in all password fields."}), 422

    if new_password != confirm_password:
        return jsonify({"success": False, "message": "New passwords do not match."}), 422

    is_valid, msg = validate_password_strength(new_password)
    if not is_valid:
        return jsonify({"success": False, "message": f"Password does not meet the minimum requirements: {msg}"}), 422

    new_hash = generate_password_hash(new_password)
    success, message = db.change_user_password(user_id, current_password, new_hash)
    
    if not success:
        return jsonify({"success": False, "message": message}), 400

    return jsonify({"success": True, "message": message}), 200


# ============================================================
# EMPLOYEE ROUTES & APIS
# ============================================================

@app.route("/employee/dashboard")
@login_required
@role_required("employee")
def employee_dashboard():
    user_id = session["user_id"]
    emp = db.get_employee_by_user_id(user_id)
    if not emp:
        flash("Employee profile not found.", "danger")
        return redirect(url_for("logout"))

    metrics = db.get_employee_dashboard_metrics(emp["employee_id"])
    appraisals = db.get_appraisals(employee_id=emp["employee_id"])
    active_appraisal = appraisals[0] if appraisals else None
    recent_logs = db.get_audit_logs(limit=10, user_id=user_id)

    return render_template(
        "employee/dashboard.html",
        active_page="dashboard",
        employee=emp,
        metrics=metrics,
        active_appraisal=active_appraisal,
        recent_logs=recent_logs
    )


@app.route("/employee/appraisal")
@login_required
@role_required("employee")
def employee_appraisal():
    user_id = session["user_id"]
    emp = db.get_employee_by_user_id(user_id)
    appraisals = db.get_appraisals(employee_id=emp["employee_id"])
    active_appraisal = appraisals[0] if appraisals else None
    history = appraisals[1:] if len(appraisals) > 1 else []

    return render_template(
        "employee/appraisal.html",
        active_page="appraisal",
        employee=emp,
        active_appraisal=active_appraisal,
        history=history
    )


@app.route("/employee/appeals")
@login_required
@role_required("employee")
def employee_appeals():
    emp = db.get_employee_by_user_id(session["user_id"])
    appeals = db.get_appeals(employee_id=emp["employee_id"])
    appraisals = db.get_appraisals(employee_id=emp["employee_id"])
    return render_template(
        "employee/appeals.html",
        active_page="appeals",
        employee=emp,
        appeals=appeals,
        appraisals=appraisals
    )


@app.route("/employee/investigations", methods=["GET", "POST"])
@login_required
@role_required("employee")
def employee_investigations():
    emp = db.get_employee_by_user_id(session["user_id"])
    if request.method == "POST":
        issue_type = request.form.get("issue_type", "Appraisal Rating Dispute / Evaluation Bias").strip()
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        evidence = request.form.get("evidence_details", "").strip() or None
        appraisal_id = request.form.get("appraisal_id") or None
        if appraisal_id:
            try:
                appraisal_id = int(appraisal_id)
            except ValueError:
                appraisal_id = None

        if not subject or not description:
            flash("Please provide both subject and detailed description of the complaint.", "danger")
        else:
            db.create_investigation(
                employee_id=emp["employee_id"],
                manager_id=emp.get("manager_id"),
                higher_authority_id=None,
                issue_type=issue_type,
                subject=subject,
                description=description,
                evidence_details=evidence,
                appraisal_id=appraisal_id
            )
            flash("HR Complaint registered securely. HR administration will investigate.", "success")
            return redirect(url_for("employee_investigations"))

    investigations = db.get_investigations(employee_id=emp["employee_id"])
    appraisals = db.get_appraisals(employee_id=emp["employee_id"])
    appeals = db.get_appeals(employee_id=emp["employee_id"])
    return render_template(
        "employee/investigations.html",
        active_page="investigations",
        employee=emp,
        investigations=investigations,
        appraisals=appraisals,
        appeals=appeals
    )


@app.route("/employee/claims", methods=["GET", "POST"])
@login_required
@role_required("employee")
def employee_claims():
    emp = db.get_employee_by_user_id(session["user_id"])
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        appraisal_period = request.form.get("appraisal_period", "FY2026-Q1").strip()
        work_date = request.form.get("work_date") or None
        document_reference = request.form.get("document_reference", "").strip() or None

        if not title or not description:
            flash("Please provide both title and description for your claim.", "danger")
        else:
            db.create_claim(
                employee_id=emp["employee_id"],
                appraisal_period=appraisal_period,
                title=title,
                description=description,
                work_date=work_date,
                document_reference=document_reference
            )
            flash("Additional work claim submitted successfully!", "success")
            return redirect(url_for("employee_claims"))

    claims = db.get_claims_by_employee(emp["employee_id"])
    return render_template(
        "employee/claims.html",
        active_page="claims",
        employee=emp,
        claims=claims
    )


@app.route("/employee/promotions", methods=["GET", "POST"])
@login_required
@role_required("employee")
def employee_promotions():
    emp = db.get_employee_by_user_id(session["user_id"])
    task_avg, review_count = db.calculate_task_average(emp["employee_id"])
    eligibility = db.check_promotion_eligibility(emp["employee_id"])
    tasks = db.get_tasks_by_employee(emp["employee_id"])
    history = db.get_promotions_history(employee_id=emp["employee_id"])

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        doc_ref = request.form.get("document_reference", "").strip() or None

        if not eligibility["eligible"]:
            flash(f"Promotion appeal rejected: Task average rating ({task_avg:.2f}) must be strictly greater than 4.60.", "danger")
            return redirect(url_for("employee_promotions"))

        if not reason:
            flash("Please state your justification and achievements for promotion.", "danger")
            return redirect(url_for("employee_promotions"))

        db.create_promotion_request(
            employee_id=emp["employee_id"],
            manager_id=emp.get("manager_id"),
            reason=reason,
            document_reference=doc_ref,
            task_average=task_avg
        )
        flash("Promotion appeal submitted to HR! Official review decision will be sent to your Gmail.", "success")
        return redirect(url_for("employee_promotions"))

    return render_template(
        "employee/promotions.html",
        active_page="promotions",
        employee=emp,
        task_avg=task_avg,
        review_count=review_count,
        eligibility=eligibility,
        tasks=tasks,
        history=history
    )


@app.route("/employee/projects")
@login_required
@role_required("employee")
def employee_projects():
    emp = db.get_employee_by_user_id(session["user_id"])
    projects = db.get_projects(emp["employee_id"])
    tasks = db.get_tasks_by_employee(emp["employee_id"])
    task_avg, review_count = db.calculate_task_average(emp["employee_id"])
    return render_template(
        "employee/projects.html",
        active_page="projects",
        employee=emp,
        projects=projects,
        tasks=tasks,
        task_avg=task_avg,
        review_count=review_count
    )


@app.route("/employee/tasks/submit", methods=["POST"])
@login_required
@role_required("employee")
def employee_submit_task():
    emp = db.get_employee_by_user_id(session["user_id"])
    task_id = request.form.get("task_id")
    status = request.form.get("status", "COMPLETED").strip().upper()
    result = request.form.get("employee_result", "").strip() or None
    reason = request.form.get("employee_reason", "").strip() or None

    if not task_id:
        flash("Invalid task selected.", "danger")
        return redirect(url_for("employee_projects"))

    db.submit_task_result(int(task_id), emp["employee_id"], status, employee_result=result, employee_reason=reason)
    flash(f"Task status updated to {status}.", "success")
    return redirect(url_for("employee_projects"))


@app.route("/employee/documents")
@login_required
@role_required("employee")
def employee_documents():
    emp = db.get_employee_by_user_id(session["user_id"])
    documents = db.get_documents(employee_id=emp["employee_id"])
    return render_template(
        "employee/documents.html",
        active_page="documents",
        employee=emp,
        documents=documents
    )


# ============================================================
# MANAGER ROUTES & APIS
# ============================================================

@app.route("/manager/dashboard")
@login_required
@role_required("manager")
def manager_dashboard():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    metrics = db.get_manager_dashboard_metrics(user_id)
    team = db.get_team_members(user_id)
    appraisals = db.get_appraisals(manager_id=user_id)

    return render_template(
        "manager/dashboard.html",
        active_page="dashboard",
        manager=mgr,
        metrics=metrics,
        team=team,
        appraisals=appraisals
    )


@app.route("/manager/claims", methods=["GET", "POST"])
@login_required
@role_required("manager")
def manager_claims():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    if request.method == "POST":
        claim_id = int(request.form.get("claim_id"))
        status = request.form.get("status", "APPROVED").strip().upper()
        comments = request.form.get("comments", "").strip() or None
        db.review_claim(claim_id, user_id, status, manager_comments=comments)
        flash(f"Claim #{claim_id} review recorded as {status}.", "success")
        return redirect(url_for("manager_claims"))

    claims = db.get_claims_for_manager(user_id)
    return render_template("manager/claims.html", active_page="claims", manager=mgr, claims=claims)


@app.route("/manager/projects")
@login_required
@role_required("manager")
def manager_projects():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    team_members = db.get_team_members(user_id)
    all_projects = []
    for member in team_members:
        member_projs = db.get_projects(member["employee_id"])
        all_projects.extend(member_projs)
    tasks = db.get_tasks_by_manager(user_id)
    return render_template(
        "manager/projects.html",
        active_page="projects",
        manager=mgr,
        projects=all_projects,
        tasks=tasks,
        team=team_members
    )


@app.route("/manager/tasks/review", methods=["POST"])
@login_required
@role_required("manager")
def manager_review_task():
    user_id = session["user_id"]
    task_id = int(request.form.get("task_id"))
    try:
        rating = float(request.form.get("rating", 5.0))
    except ValueError:
        rating = 5.0
    comments = request.form.get("comments", "").strip() or None

    db.review_task(task_id, user_id, rating, comments=comments)
    flash(f"Task #{task_id} successfully scored {rating:.2f}/5.00 with manager feedback!", "success")
    return redirect(url_for("manager_projects"))


@app.route("/manager/appraisals")
@login_required
@role_required("manager")
def manager_appraisals():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    appraisals = db.get_appraisals(manager_id=user_id)
    return render_template(
        "manager/appraisals.html",
        active_page="appraisals",
        manager=mgr,
        appraisals=appraisals
    )


@app.route("/manager/appeals")
@login_required
@role_required("manager")
def manager_appeals():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    appeals = db.get_appeals(manager_user_id=user_id)
    return render_template(
        "manager/appeals.html",
        active_page="appeals",
        manager=mgr,
        appeals=appeals
    )


@app.route("/manager/documents")
@login_required
@role_required("manager")
def manager_documents():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    documents = db.get_documents(manager_user_id=user_id)
    return render_template(
        "manager/documents.html",
        active_page="documents",
        manager=mgr,
        documents=documents
    )


@app.route("/manager/team")
@login_required
@role_required("manager")
def manager_team():
    user_id = session["user_id"]
    mgr = db.get_employee_by_user_id(user_id)
    team = db.get_team_members(user_id)
    return render_template(
        "manager/team.html",
        active_page="team",
        manager=mgr,
        team=team
    )


# ============================================================
# HR ROUTES & APIS
# ============================================================

@app.route("/hr/dashboard")
@login_required
@role_required("hr")
def hr_dashboard():
    metrics = db.get_hr_dashboard_metrics()
    recent_logs = db.get_audit_logs(limit=8)
    investigations = db.get_investigations()
    promotion_requests = db.get_promotion_requests_for_hr(status="SUBMITTED")
    return render_template(
        "hr/dashboard.html",
        active_page="dashboard",
        metrics=metrics,
        recent_logs=recent_logs,
        investigations=investigations,
        promotion_requests=promotion_requests
    )


@app.route("/hr/promotions")
@login_required
@role_required("hr")
def hr_promotions():
    status_filter = request.args.get("status")
    requests = db.get_promotion_requests_for_hr(status=status_filter)
    history = db.get_promotions_history()
    return render_template(
        "hr/promotions.html",
        active_page="promotions",
        requests=requests,
        history=history,
        status_filter=status_filter
    )


@app.route("/hr/promotions/<int:request_id>/approve", methods=["POST"])
@login_required
@role_required("hr")
def hr_approve_promotion(request_id):
    hr_response = request.form.get("hr_response", "Promotion approved on verified performance merit.").strip()
    new_designation = request.form.get("new_designation", "Engineering Manager").strip()

    temp_password = "Mgr@" + secrets.token_hex(4) + "!"
    temp_pwd_hash = generate_password_hash(temp_password)

    try:
        result = db.approve_promotion_transaction(
            request_id=request_id,
            hr_user_id=session["user_id"],
            temp_password_hash=temp_pwd_hash,
            hr_response=hr_response,
            new_designation=new_designation
        )

        # Dispatch official promotion email via SMTP
        email_service.send_promotion_email(
            to_address=result["email"],
            employee_name=result["name"],
            new_role=result["new_role"],
            new_designation=result["new_designation"],
            temp_password=temp_password,
            task_average=result["task_average"]
        )

        flash(f"🎉 Promotion approved for {result['name']}! Official Gmail dispatched with temporary password: {temp_password}", "success")
    except Exception as e:
        flash(f"Promotion approval failed: {str(e)}", "danger")

    return redirect(url_for("hr_promotions"))


@app.route("/hr/promotions/<int:request_id>/reject", methods=["POST"])
@login_required
@role_required("hr")
def hr_reject_promotion(request_id):
    hr_response = request.form.get("hr_response", "Promotion criteria not met at this time.").strip()
    db.reject_promotion_request(request_id, session["user_id"], hr_response)
    flash(f"Promotion request #{request_id} rejected with feedback.", "info")
    return redirect(url_for("hr_promotions"))


@app.route("/hr/investigations")
@login_required
@role_required("hr")
def hr_investigations():
    investigations = db.get_investigations()
    return render_template(
        "hr/investigations.html",
        active_page="investigations",
        investigations=investigations
    )


@app.route("/hr/investigations/resolve", methods=["POST"])
@login_required
@role_required("hr")
def hr_resolve_investigation():
    inv_id = int(request.form.get("investigation_id"))
    status = request.form.get("status", "RESOLVED_UPHELD")
    response_notes = request.form.get("authority_response", "").strip() or None

    db.resolve_investigation(inv_id, session["user_id"], status, authority_response=response_notes)
    flash(f"Investigation #{inv_id} resolved with status {status}.", "success")
    return redirect(url_for("hr_investigations"))


@app.route("/hr/employees")
@login_required
@role_required("hr")
def hr_employees():
    search = request.args.get("search", "")
    department = request.args.get("department", "")
    employees = db.get_employees(search=search, department=department)
    managers = [e for e in employees if e["role"] == "manager"]
    return render_template(
        "hr/employees.html",
        active_page="employees",
        employees=employees,
        managers=managers,
        search=search,
        department=department
    )


@app.route("/hr/appraisals")
@login_required
@role_required("hr")
def hr_appraisals():
    appraisals = db.get_appraisals()
    return render_template(
        "hr/appraisals.html",
        active_page="appraisals",
        appraisals=appraisals
    )


@app.route("/hr/reports")
@login_required
@role_required("hr")
def hr_reports():
    reports = db.get_hr_reports()
    return render_template(
        "hr/reports.html",
        active_page="reports",
        reports=reports
    )


# ============================================================
# ADMINISTRATOR ROLE ROUTES
# ============================================================

@app.route("/administrator/dashboard")
@login_required
@role_required("administrator")
def administrator_dashboard():
    metrics = db.get_admin_dashboard_metrics()
    projects = db.get_all_projects_admin()
    tasks = db.get_all_tasks_admin()
    employees = db.get_all_employees_admin()
    claims = db.get_all_claims_admin()
    recent_logs = db.get_audit_logs(limit=10)
    return render_template(
        "administrator/dashboard.html",
        active_page="dashboard",
        metrics=metrics,
        projects=projects,
        tasks=tasks,
        employees=employees,
        claims=claims,
        recent_logs=recent_logs
    )


@app.route("/administrator/projects", methods=["GET", "POST"])
@login_required
@role_required("administrator")
def administrator_projects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        employee_id = int(request.form.get("employee_id"))
        category = request.form.get("category", "General").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Medium").strip()
        due_date = request.form.get("due_date") or None

        if not name or not employee_id:
            flash("Project name and assigned employee are required.", "danger")
        else:
            db.create_project_admin(name, employee_id, category, description, priority, due_date)
            flash(f"Project '{name}' created and assigned successfully!", "success")
            return redirect(url_for("administrator_projects"))

    projects = db.get_all_projects_admin()
    employees = db.get_all_employees_admin()
    return render_template(
        "administrator/projects.html",
        active_page="projects",
        projects=projects,
        employees=employees
    )


@app.route("/administrator/tasks", methods=["GET", "POST"])
@login_required
@role_required("administrator")
def administrator_tasks():
    if request.method == "POST":
        project_id = int(request.form.get("project_id"))
        employee_id = int(request.form.get("employee_id"))
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date = request.form.get("due_date") or None

        if not title:
            flash("Task title is required.", "danger")
        else:
            db.create_project_task(project_id, employee_id, session["user_id"], title, description, due_date)
            flash(f"Task '{title}' assigned successfully!", "success")
            return redirect(url_for("administrator_tasks"))

    tasks = db.get_all_tasks_admin()
    projects = db.get_all_projects_admin()
    employees = db.get_all_employees_admin()
    return render_template(
        "administrator/tasks.html",
        active_page="tasks",
        tasks=tasks,
        projects=projects,
        employees=employees
    )


@app.route("/administrator/audit-logs")
@login_required
@role_required("administrator")
def administrator_audit_logs():
    logs = db.get_audit_logs(limit=200)
    return render_template(
        "administrator/audit_logs.html",
        active_page="audit_logs",
        logs=logs
    )


@app.route("/hr/audit-logs")
@login_required
@role_required("hr")
def hr_audit_logs():
    logs = db.get_audit_logs(limit=200)
    return render_template(
        "hr/audit_logs.html",
        active_page="audit_logs",
        logs=logs
    )


@app.route("/hr/projects")
@login_required
@role_required("hr")
def hr_projects():
    projects = db.get_projects()
    return render_template(
        "hr/projects.html",
        active_page="projects",
        projects=projects
    )


# ============================================================
# REST APIS: AUTH & SESSION
# ============================================================

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 422

    user = db.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"success": False, "message": "Invalid email address or password."}), 401

    session.clear()
    session["user_id"] = user["user_id"]
    session["name"] = user["name"]
    session["email"] = user["email"]
    session["role"] = user["role"].lower()
    session["must_change_password"] = bool(user.get("must_change_password"))
    session["user"] = {
        "id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"].lower(),
        "must_change_password": bool(user.get("must_change_password"))
    }

    db.create_audit_log(user["user_id"], "LOGIN", "USER", user["user_id"], f"User {user['email']} logged in via API.")

    redirect_url = url_for("employee_dashboard")
    role = user["role"].lower()
    if role == "manager":
        redirect_url = url_for("manager_dashboard")
    elif role in ("hr", "admin"):
        redirect_url = url_for("hr_dashboard")
    elif role == "administrator":
        redirect_url = url_for("administrator_dashboard")

    return jsonify({
        "success": True,
        "otp_required": False,
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"].lower(),
        "redirect_url": redirect_url,
        "message": "Login successful.",
        "user": session["user"],
        "must_change_password": session["must_change_password"]
    }), 200


@app.route("/api/verify-otp", methods=["POST"])
def api_verify_otp():
    return jsonify({"success": True, "message": "OTP verification is disabled."}), 200


@app.route("/api/force-password-change", methods=["POST"])
@login_required
def api_force_password_change():
    data = request.get_json() or {}
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not new_password or not confirm_password:
        return jsonify({"success": False, "message": "Please provide both new_password and confirm_password."}), 422

    if new_password != confirm_password:
        return jsonify({"success": False, "message": "New passwords do not match."}), 422

    is_valid, msg = validate_password_strength(new_password)
    if not is_valid:
        return jsonify({"success": False, "message": f"Password requirements not met: {msg}"}), 422

    new_hash = generate_password_hash(new_password)
    db.force_update_user_password(session["user_id"], new_hash)
    session["must_change_password"] = False
    if "user" in session:
        session["user"]["must_change_password"] = False

    return jsonify({"success": True, "message": "Temporary password updated successfully."}), 200


@app.route("/api/logout", methods=["POST"])
def api_logout():
    user_id = session.get("user_id")
    if user_id:
        db.create_audit_log(user_id, "LOGOUT", "USER", user_id, "User signed out.")
    session.clear()
    return jsonify({"success": True, "message": "Signed out successfully"}), 200


@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    return jsonify({
        "success": True,
        "user": {
            "id": session.get("user_id"),
            "name": session.get("name"),
            "email": session.get("email"),
            "role": session.get("role")
        }
    }), 200


# ============================================================
# REST APIS: PROJECTS
# ============================================================

@app.route("/api/projects", methods=["GET"])
@login_required
def api_get_projects():
    role = session.get("role")
    if role == "employee":
        emp = db.get_employee_by_user_id(session["user_id"])
        projects = db.get_projects(emp["employee_id"])
    elif role == "manager":
        team = db.get_team_members(session["user_id"])
        projects = []
        for member in team:
            projects.extend(db.get_projects(member["employee_id"]))
    else:
        projects = db.get_projects()

    return jsonify({"success": True, "data": projects}), 200


@app.route("/api/projects", methods=["POST"])
@login_required
@role_required("employee", "manager")
def api_create_project():
    data = request.get_json() or {}
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Employee profile not found"}), 404

    name = data.get("name", "").strip()
    category = data.get("category", "").strip()
    description = data.get("description", "").strip()
    priority = data.get("priority", "Medium")
    due_date = data.get("due_date") or None

    if not name:
        return jsonify({"success": False, "message": "Project title is required"}), 422

    progress = int(data.get("progress", 0))
    status = data.get("status", "pending")
    completed = int(data.get("milestones_completed", 0))
    total = int(data.get("milestones_total", 0))

    project_id = db.create_project(
        employee_id=emp["employee_id"],
        name=name,
        category=category,
        description=description,
        progress=progress,
        status=status,
        priority=priority,
        due_date=due_date,
        milestones_completed=completed,
        milestones_total=total
    )

    db.create_audit_log(session["user_id"], "CREATE_PROJECT", "PROJECT", project_id, f"Created project: '{name}'.")
    return jsonify({"success": True, "message": "Project created successfully", "data": {"project_id": project_id}}), 201


@app.route("/api/projects/<int:project_id>", methods=["PUT"])
@login_required
def api_update_project(project_id):
    proj = db.get_project_by_id(project_id)
    if not proj:
        return jsonify({"success": False, "message": "Project not found"}), 404

    # Permission check
    if session.get("role") == "employee" and proj["employee_user_id"] != session["user_id"]:
        return jsonify({"success": False, "message": "You are not authorized to modify this project"}), 403

    data = request.get_json() or {}
    name = data.get("name", proj["name"]).strip()
    category = data.get("category", proj["category"])
    description = data.get("description", proj["description"])
    progress = int(data.get("progress", proj["progress"]))
    status = data.get("status", proj["status"])
    priority = data.get("priority", proj["priority"])
    due_date = data.get("due_date", proj["due_date"]) or None
    completed = int(data.get("milestones_completed", proj["milestones_completed"]))
    total = int(data.get("milestones_total", proj["milestones_total"]))

    db.update_project(project_id, name, category, description, progress, status, priority, due_date, completed, total)
    db.create_audit_log(session["user_id"], "UPDATE_PROJECT", "PROJECT", project_id, f"Updated project: '{name}'.")
    return jsonify({"success": True, "message": "Project updated successfully"}), 200


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
@login_required
def api_delete_project(project_id):
    proj = db.get_project_by_id(project_id)
    if not proj:
        return jsonify({"success": False, "message": "Project not found"}), 404

    if session.get("role") == "employee" and proj["employee_user_id"] != session["user_id"]:
        return jsonify({"success": False, "message": "You are not authorized to delete this project"}), 403

    db.delete_project(project_id)
    db.create_audit_log(session["user_id"], "DELETE_PROJECT", "PROJECT", project_id, f"Deleted project #{project_id}.")
    return jsonify({"success": True, "message": "Project deleted successfully"}), 200


# ============================================================
# REST APIS: APPRAISALS WORKFLOW
# ============================================================

@app.route("/api/employee/appraisals", methods=["GET"])
@login_required
@role_required("employee")
def api_get_employee_appraisals():
    emp = db.get_employee_by_user_id(session["user_id"])
    appraisals = db.get_appraisals(employee_id=emp["employee_id"])
    return jsonify({"success": True, "data": appraisals}), 200


@app.route("/api/manager/appraisals", methods=["GET"])
@login_required
@role_required("manager")
def api_get_manager_appraisals():
    appraisals = db.get_appraisals(manager_id=session["user_id"])
    return jsonify({"success": True, "data": appraisals}), 200


@app.route("/api/appraisals/<int:appraisal_id>", methods=["GET"])
@login_required
def api_get_appraisal_by_id(appraisal_id):
    appraisal = db.get_appraisal_by_id(appraisal_id)
    if not appraisal:
        return jsonify({"success": False, "message": "Appraisal not found"}), 404

    # Access control
    role = session.get("role", "").lower()
    user_id = session.get("user_id")
    if role == "employee" and appraisal["employee_user_id"] != user_id:
        return jsonify({"success": False, "message": "Access denied"}), 403
    if role == "manager" and appraisal["manager_id"] != user_id:
        return jsonify({"success": False, "message": "Access denied"}), 403

    return jsonify({"success": True, "data": appraisal}), 200


@app.route("/api/appraisals", methods=["POST"])
@login_required
@role_required("employee")
def api_create_appraisal():
    user_id = session["user_id"]
    emp = db.get_employee_by_user_id(user_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee profile not found"}), 404

    data = request.get_json() or {}
    period = data.get("appraisal_period", "").strip()
    self_rating = data.get("self_rating")
    comments = data.get("employee_comments", "").strip()
    manager_id = data.get("manager_id")
    hr_id = data.get("hr_id")

    if not period or self_rating is None or not comments or not manager_id or not hr_id:
        return jsonify({"success": False, "message": "Appraisal period, manager, HR, self rating, and comments are required"}), 422

    try:
        manager_id = int(manager_id)
        hr_id = int(hr_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Manager and HR selections are invalid"}), 422

    if not db.is_user_in_roles(manager_id, ("manager",)):
        return jsonify({"success": False, "message": "Selected manager is invalid"}), 422
    if not db.is_user_in_roles(hr_id, ("hr", "admin")):
        return jsonify({"success": False, "message": "Selected HR user is invalid"}), 422

    try:
        self_rating_val = float(self_rating)
        if self_rating_val < Config.MIN_RATING or self_rating_val > Config.MAX_RATING:
            return jsonify({"success": False, "message": f"Self rating must be between {Config.MIN_RATING} and {Config.MAX_RATING}"}), 422
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid rating format"}), 422

    appraisal_id = db.create_appraisal(
        employee_id=emp["employee_id"],
        manager_id=manager_id,
        hr_id=hr_id,
        appraisal_period=period,
        self_rating=self_rating_val,
        employee_comments=comments,
        status="UNDER_REVIEW"
    )

    db.create_audit_log(user_id, "SUBMIT_APPRAISAL", "APPRAISAL", appraisal_id, f"Submitted self-appraisal for {period} with status UNDER_REVIEW.")
    return jsonify({"success": True, "message": "Appraisal submitted successfully.", "data": {"appraisal_id": appraisal_id}}), 201


@app.route("/api/appraisals/<int:appraisal_id>/review", methods=["POST"])
@login_required
@role_required("manager", "hr")
def api_review_appraisal(appraisal_id):
    reviewer_id = session["user_id"]
    appraisal = db.get_appraisal_by_id(appraisal_id)
    if not appraisal:
        return jsonify({"success": False, "message": "Appraisal not found"}), 404
    if session.get("role", "").lower() == "manager" and appraisal["manager_id"] != reviewer_id:
        return jsonify({"success": False, "message": "You are not assigned to review this appraisal"}), 403

    data = request.get_json() or {}
    status = data.get("status", "").upper()
    manager_rating = data.get("overall_rating")
    manager_comments = data.get("manager_comments", "").strip()

    valid_statuses = ("APPROVED", "REJECTED", "CHANGES_REQUESTED")
    if status not in valid_statuses:
        return jsonify({"success": False, "message": f"Invalid review status. Must be one of: {', '.join(valid_statuses)}"}), 422

    rating_val = None
    if manager_rating is not None and str(manager_rating).strip() != "":
        try:
            rating_val = float(manager_rating)
            if rating_val < Config.MIN_RATING or rating_val > Config.MAX_RATING:
                return jsonify({"success": False, "message": f"Rating must be between {Config.MIN_RATING} and {Config.MAX_RATING}"}), 422
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Invalid rating value"}), 422

    db.review_appraisal_transaction(
        appraisal_id=appraisal_id,
        manager_id=reviewer_id,
        overall_rating=rating_val,
        manager_comments=manager_comments,
        status=status
    )

    db.create_audit_log(reviewer_id, "REVIEW_APPRAISAL", "APPRAISAL", appraisal_id, f"Reviewer saved appraisal #{appraisal_id}: status set to {status}.")
    return jsonify({"success": True, "message": f"Appraisal review saved with status {status}"}), 200


# ============================================================
# REST APIS: DOCUMENTS & VERIFICATION
# ============================================================

@app.route("/api/documents", methods=["GET"])
@login_required
def api_get_documents():
    role = session.get("role")
    if role == "employee":
        emp = db.get_employee_by_user_id(session["user_id"])
        docs = db.get_documents(employee_id=emp["employee_id"])
    elif role == "manager":
        docs = db.get_documents(manager_user_id=session["user_id"])
    else:
        docs = db.get_documents()

    return jsonify({"success": True, "data": docs}), 200


@app.route("/api/documents/upload", methods=["POST"])
@login_required
@role_required("employee")
def api_upload_document():
    user_id = session["user_id"]
    emp = db.get_employee_by_user_id(user_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee not found"}), 404

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file payload attached"}), 400

    file = request.files["file"]
    doc_type = request.form.get("document_type", "General Proof").strip()

    if file.filename == "":
        return jsonify({"success": False, "message": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "File format not allowed"}), 415

    original_filename = secure_filename(file.filename)
    safe_name = f"doc_{emp['employee_id']}_{original_filename}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    file.save(save_path)

    relative_path = f"uploads/documents/{safe_name}"
    doc_id = db.create_document(
        employee_id=emp["employee_id"],
        document_type=doc_type,
        document_name=original_filename,
        document_path=relative_path
    )

    db.create_audit_log(user_id, "UPLOAD_DOCUMENT", "DOCUMENT", doc_id, f"Uploaded document: '{original_filename}'.")
    return jsonify({"success": True, "message": "Document uploaded successfully", "data": {"document_id": doc_id}}), 201


@app.route("/api/documents/<int:document_id>/resubmit", methods=["POST"])
@login_required
@role_required("employee")
def api_resubmit_document(document_id):
    doc = db.get_document_by_id(document_id)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404

    if doc["employee_user_id"] != session["user_id"]:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No replacement file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "File format not supported"}), 415

    original_filename = secure_filename(file.filename)
    safe_name = f"resubmit_{doc['employee_id']}_{original_filename}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    file.save(save_path)

    relative_path = f"uploads/documents/{safe_name}"
    db.resubmit_document(document_id, original_filename, relative_path)
    db.create_audit_log(session["user_id"], "RESUBMIT_DOCUMENT", "DOCUMENT", document_id, f"Resubmitted document #{document_id}.")

    return jsonify({"success": True, "message": "Document resubmitted successfully"}), 200


@app.route("/api/documents/<int:document_id>/review", methods=["POST"])
@login_required
@role_required("manager", "hr")
def api_review_document(document_id):
    manager_id = session["user_id"]
    doc = db.get_document_by_id(document_id)
    if not doc:
        return jsonify({"success": False, "message": "Document not found"}), 404

    data = request.get_json() or {}
    action = data.get("action", "").lower()
    comments = data.get("comments", "").strip()

    if action not in ("approved", "rejected", "resubmit"):
        return jsonify({"success": False, "message": "Invalid review action"}), 422

    db.review_document_transaction(document_id, manager_id, action, comments)
    db.create_audit_log(manager_id, "REVIEW_DOCUMENT", "DOCUMENT", document_id, f"Document #{document_id} set to {action}.")

    return jsonify({"success": True, "message": f"Document marked as {action}"}), 200


# ============================================================
# REST APIS: APPEALS WORKFLOW
# ============================================================

@app.route("/api/appeals", methods=["POST"])
@login_required
@role_required("employee")
def api_create_appeal():
    user_id = session["user_id"]
    emp = db.get_employee_by_user_id(user_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee not found"}), 404

    data = request.get_json() or {}
    appraisal_id = data.get("appraisal_id")
    manager_id = data.get("manager_id")
    hr_id = data.get("hr_id")
    reason = data.get("reason", "").strip()

    if not appraisal_id or not manager_id or not hr_id or not reason:
        return jsonify({"success": False, "message": "Appraisal, manager, HR, and appeal reason are required"}), 422

    try:
        appraisal_id = int(appraisal_id)
        manager_id = int(manager_id)
        hr_id = int(hr_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Appraisal, manager, or HR selection is invalid"}), 422

    if not db.is_user_in_roles(manager_id, ("manager",)):
        return jsonify({"success": False, "message": "Selected manager is invalid"}), 422
    if not db.is_user_in_roles(hr_id, ("hr", "admin")):
        return jsonify({"success": False, "message": "Selected HR user is invalid"}), 422

    appraisal = db.get_appraisal_by_id(appraisal_id)
    if not appraisal or appraisal["employee_id"] != emp["employee_id"]:
        return jsonify({"success": False, "message": "Appraisal record invalid or does not belong to you"}), 403

    appeal_id = db.create_appeal(appraisal_id, emp["employee_id"], manager_id, hr_id, reason)
    db.create_audit_log(user_id, "SUBMIT_APPEAL", "APPEAL", appeal_id, f"Submitted reconsideration appeal for appraisal #{appraisal_id}.")

    return jsonify({"success": True, "message": "Appeal submitted successfully.", "data": {"appeal_id": appeal_id}}), 201


@app.route("/api/employee/appeals", methods=["GET"])
@login_required
@role_required("employee")
def api_get_employee_appeals():
    emp = db.get_employee_by_user_id(session["user_id"])
    appeals = db.get_appeals(employee_id=emp["employee_id"])
    return jsonify({"success": True, "data": appeals}), 200


@app.route("/api/manager/appeals", methods=["GET"])
@login_required
@role_required("manager")
def api_get_manager_appeals():
    appeals = db.get_appeals(manager_user_id=session["user_id"])
    return jsonify({"success": True, "data": appeals}), 200


@app.route("/api/appeals/<int:appeal_id>/review", methods=["POST"])
@login_required
@role_required("manager", "hr")
def api_review_appeal(appeal_id):
    reviewer_id = session["user_id"]
    appeal = db.get_appeal_by_id(appeal_id)
    if not appeal:
        return jsonify({"success": False, "message": "Appeal not found"}), 404
    if session.get("role", "").lower() == "manager" and appeal["manager_id"] != reviewer_id:
        return jsonify({"success": False, "message": "You are not assigned to review this appeal"}), 403

    data = request.get_json() or {}
    status = data.get("status", "").lower()
    manager_response = data.get("manager_response", "").strip()
    appraisal_status = data.get("appraisal_status")

    if status not in ("approved", "rejected"):
        return jsonify({"success": False, "message": "Status must be 'approved' or 'rejected'"}), 422
    if not manager_response:
        return jsonify({"success": False, "message": "Manager response comment is required"}), 422

    db.review_appeal(appeal_id, status, manager_response, appraisal_status)
    db.create_audit_log(reviewer_id, "REVIEW_APPEAL", "APPEAL", appeal_id, f"Reviewer decided appeal #{appeal_id} as {status}.")

    return jsonify({"success": True, "message": f"Appeal decision recorded as {status}"}), 200


# ============================================================
# REST APIS: INVESTIGATIONS / HR COMPLAINTS
# ============================================================

@app.route("/api/investigations", methods=["POST"])
@login_required
@role_required("employee")
def api_create_investigation():
    user_id = session["user_id"]
    emp = db.get_employee_by_user_id(user_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee not found"}), 404

    data = request.get_json() or {}
    issue_type = data.get("issue_type", "").strip()
    subject = data.get("subject", "").strip()
    description = data.get("description", "").strip()
    evidence = data.get("evidence_details", "").strip()
    appraisal_id = data.get("appraisal_id") or None
    appeal_id = data.get("appeal_id") or None

    if not issue_type or not subject or not description:
        return jsonify({"success": False, "message": "Complaint reason/issue type, subject, and description are required"}), 422

    hr_user = db.get_primary_hr_user()
    if not hr_user:
        return jsonify({"success": False, "message": "No HR account is currently available"}), 422

    inv_id = db.create_investigation(
        employee_id=emp["employee_id"],
        manager_id=emp["manager_id"],
        higher_authority_id=hr_user["user_id"],
        issue_type=issue_type,
        subject=subject,
        description=description,
        evidence_details=evidence,
        appraisal_id=appraisal_id,
        appeal_id=appeal_id
    )

    db.create_audit_log(user_id, "CREATE_INVESTIGATION", "INVESTIGATION", inv_id, f"Submitted complaint/escalation to HR: '{subject}'.")
    return jsonify({"success": True, "message": "Complaint submitted to HR.", "data": {"investigation_id": inv_id}}), 201


@app.route("/api/employee/investigations", methods=["GET"])
@login_required
@role_required("employee")
def api_get_employee_investigations():
    emp = db.get_employee_by_user_id(session["user_id"])
    invs = db.get_investigations(employee_id=emp["employee_id"])
    return jsonify({"success": True, "data": invs}), 200


@app.route("/api/hr/investigations", methods=["GET"])
@login_required
@role_required("hr")
def api_get_hr_investigations():
    invs = db.get_investigations()
    return jsonify({"success": True, "data": invs}), 200


@app.route("/api/investigations/<int:investigation_id>/review", methods=["POST"])
@login_required
@role_required("hr")
def api_review_investigation(investigation_id):
    hr_user_id = session["user_id"]
    inv = db.get_investigation_by_id(investigation_id)
    if not inv:
        return jsonify({"success": False, "message": "Investigation not found"}), 404

    data = request.get_json() or {}
    status = data.get("status", "").upper()
    response = data.get("authority_response", "").strip()

    valid_statuses = ("UNDER_INVESTIGATION", "RESOLVED_UPHELD", "RESOLVED_REJECTED")
    if status not in valid_statuses:
        return jsonify({"success": False, "message": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 422
    if not response:
        return jsonify({"success": False, "message": "Official HR authority response is required"}), 422

    db.review_investigation(investigation_id, status, response, hr_user_id)
    db.create_audit_log(hr_user_id, "REVIEW_INVESTIGATION", "INVESTIGATION", investigation_id, f"HR ruled on complaint #{investigation_id}: {status}.")

    return jsonify({"success": True, "message": f"Investigation status updated to {status.replace('_', ' ')}"}), 200


# ============================================================
# REST APIS: HR EMPLOYEE MANAGEMENT & REPORTS
# ============================================================

@app.route("/api/employees", methods=["GET"])
@login_required
@role_required("hr")
def api_get_employees():
    search = request.args.get("search", "")
    department = request.args.get("department", "")
    employees = db.get_employees(search=search, department=department)
    return jsonify({"success": True, "data": employees}), 200


@app.route("/api/employees", methods=["POST"])
@login_required
@role_required("hr")
def api_create_employee():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    employee_code = data.get("employee_code", "").strip()
    password = data.get("password", "")
    role = data.get("role", "employee").lower()
    age = data.get("age")
    address = data.get("address", "").strip()

    if not name or not email or not employee_code or not password:
        return jsonify({"success": False, "message": "Name, email, employee code, and password are required"}), 422

    existing_user = db.get_user_by_email(email)
    if existing_user:
        return jsonify({"success": False, "message": "Email already registered."}), 409

    is_valid, msg = validate_password_strength(password)
    if not is_valid:
        return jsonify({"success": False, "message": f"Password does not meet the minimum requirements: {msg}"}), 422

    age_val = None
    if age is not None and str(age).strip() != "":
        try:
            age_val = int(age)
            if age_val < 21:
                return jsonify({"success": False, "message": "Employees must be at least 21 years of age."}), 422
        except ValueError:
            return jsonify({"success": False, "message": "Age must be a valid number"}), 422

    pwd_hash = generate_password_hash(password)
    try:
        result = db.create_employee_transaction(
            name=name,
            email=email,
            password_hash=pwd_hash,
            role=role,
            employee_code=employee_code,
            age=age_val,
            address=address,
            department=data.get("department", "Engineering"),
            designation=data.get("designation", "Staff"),
            phone=data.get("phone", ""),
            location=data.get("location", ""),
            joining_date=data.get("joining_date") or None,
            manager_id=data.get("manager_id") or None
        )
        db.create_audit_log(session["user_id"], "CREATE_EMPLOYEE", "USER", result["user_id"], f"HR created account {email} ({employee_code}).")
        return jsonify({"success": True, "message": "Employee created successfully", "data": result}), 201
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to create employee: {str(e)}"}), 500


@app.route("/api/employees/<int:employee_id>", methods=["PUT"])
@login_required
@role_required("hr")
def api_update_employee(employee_id):
    emp = db.get_employee_by_id(employee_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee not found"}), 404

    data = request.get_json() or {}
    age_val = None
    if "age" in data and str(data.get("age")).strip() != "":
        try:
            age_val = int(data.get("age"))
        except ValueError:
            return jsonify({"success": False, "message": "Invalid age format"}), 422

    db.update_employee(
        employee_id=employee_id,
        department=data.get("department"),
        designation=data.get("designation"),
        phone=data.get("phone"),
        location=data.get("location"),
        age=age_val if "age" in data else None,
        address=data.get("address"),
        manager_id=data.get("manager_id")
    )

    db.create_audit_log(session["user_id"], "UPDATE_EMPLOYEE", "EMPLOYEE", employee_id, f"HR updated profile for {emp['employee_code']}.")
    return jsonify({"success": True, "message": "Employee profile updated successfully"}), 200


@app.route("/api/hr/reports", methods=["GET"])
@login_required
@role_required("hr")
def api_get_hr_reports():
    reports = db.get_hr_reports()
    return jsonify({"success": True, "data": reports}), 200


@app.route("/api/audit-logs", methods=["GET"])
@login_required
@role_required("hr", "administrator")
def api_get_audit_logs():
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "limit must be a whole number."}), 422
    limit = max(1, min(limit, 500))
    logs = db.get_audit_logs(limit=limit)
    return jsonify({"success": True, "data": logs}), 200


# ============================================================
# ADMINISTRATOR CONSOLE ROUTES & APIS
# ============================================================



@app.route("/api/administrator/employees", methods=["GET"])
@login_required
@role_required("administrator")
def api_admin_employees():
    employees = db.get_all_employees_admin()
    return jsonify({"success": True, "data": employees}), 200


@app.route("/api/administrator/projects", methods=["GET"])
@login_required
@role_required("administrator")
def api_admin_projects():
    projects = db.get_all_projects_admin()
    return jsonify({"success": True, "data": projects}), 200


# ============================================================
# REST APIS: CLAIMS SYSTEM
# ============================================================

@app.route("/api/claims", methods=["POST"])
@login_required
@role_required("employee")
def api_create_claim():
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Employee profile not found"}), 404

    data = request.get_json() or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    appraisal_period = data.get("appraisal_period", "").strip() or None
    work_date = data.get("work_date") or None
    document_reference = data.get("document_reference", "").strip() or None

    if not title or not description:
        return jsonify({"success": False, "message": "Claim title and description are required."}), 422

    claim_id = db.create_claim(
        employee_id=emp["employee_id"],
        appraisal_period=appraisal_period,
        title=title,
        description=description,
        work_date=work_date,
        document_reference=document_reference
    )
    return jsonify({"success": True, "message": "Claim submitted successfully.", "data": {"claim_id": claim_id}}), 201


@app.route("/api/claims", methods=["GET"])
@login_required
def api_get_claims():
    role = session.get("role", "").lower()
    if role == "employee":
        emp = db.get_employee_by_user_id(session["user_id"])
        if not emp:
            return jsonify({"success": False, "message": "Employee profile not found"}), 404
        claims = db.get_claims_by_employee(emp["employee_id"])
    elif role == "manager":
        claims = db.get_claims_for_manager(session["user_id"])
    else:  # hr, administrator
        claims = db.execute_query("""
            SELECT c.*, e.employee_code, e.department, e.designation,
                   u.name as employee_name, u.email as employee_email,
                   m.name as manager_name
            FROM claims c
            JOIN employees e ON c.employee_id = e.employee_id
            JOIN users u ON e.user_id = u.user_id
            LEFT JOIN users m ON c.manager_id = m.user_id
            ORDER BY c.created_at DESC
        """, fetchall=True) or []

    return jsonify({"success": True, "data": claims}), 200


@app.route("/api/employee/claims", methods=["GET"])
@login_required
@role_required("employee")
def api_get_employee_claims():
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Employee profile not found"}), 404
    claims = db.get_claims_by_employee(emp["employee_id"])
    return jsonify({"success": True, "data": claims}), 200


@app.route("/api/manager/claims", methods=["GET"])
@login_required
@role_required("manager", "hr")
def api_get_manager_claims():
    claims = db.get_claims_for_manager(session["user_id"])
    return jsonify({"success": True, "data": claims}), 200


@app.route("/api/claims/<int:claim_id>", methods=["GET"])
@login_required
def api_get_claim_detail(claim_id):
    claim = db.get_claim_by_id(claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim record not found."}), 404
    return jsonify({"success": True, "data": claim}), 200


@app.route("/api/claims/<int:claim_id>/review", methods=["POST"])
@login_required
@role_required("manager", "hr")
def api_review_claim(claim_id):
    data = request.get_json() or {}
    status = data.get("status", "").upper()
    comments = data.get("comments", "").strip()

    if status not in ("APPROVED", "REJECTED"):
        return jsonify({"success": False, "message": "Review status must be APPROVED or REJECTED."}), 422

    claim = db.get_claim_by_id(claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim record not found."}), 404

    db.review_claim(claim_id, session["user_id"], status, comments)
    return jsonify({"success": True, "message": f"Claim has been {status.lower()}."}), 200


# ============================================================
# REST APIS: PROJECT TASKS & REVIEWS
# ============================================================

@app.route("/api/tasks", methods=["POST"])
@login_required
@role_required("manager", "hr", "administrator")
def api_create_task():
    data = request.get_json() or {}
    project_id = data.get("project_id")
    employee_id = data.get("employee_id")
    title = data.get("title", "").strip()
    description = data.get("description", "").strip() or None
    due_date = data.get("due_date") or None

    if not project_id or not employee_id or not title:
        return jsonify({"success": False, "message": "Project, employee, and task title are required."}), 422

    try:
        project_id = int(project_id)
        employee_id = int(employee_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid project or employee ID."}), 422

    task_id = db.create_project_task(
        project_id=project_id,
        employee_id=employee_id,
        assigned_by=session["user_id"],
        title=title,
        description=description,
        due_date=due_date
    )
    return jsonify({"success": True, "message": "Task assigned successfully.", "data": {"task_id": task_id}}), 201


@app.route("/api/tasks", methods=["GET"])
@login_required
def api_get_tasks():
    role = session.get("role", "").lower()
    if role == "employee":
        emp = db.get_employee_by_user_id(session["user_id"])
        if not emp:
            return jsonify({"success": False, "message": "Employee profile not found"}), 404
        tasks = db.get_tasks_by_employee(emp["employee_id"])
    elif role == "manager":
        tasks = db.get_tasks_by_manager(session["user_id"])
    else:  # hr, administrator
        tasks = db.execute_query("""
            SELECT pt.*, p.name AS project_name, e.employee_code, e.department,
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
            ORDER BY pt.created_at DESC
        """, fetchall=True) or []

    return jsonify({"success": True, "data": tasks}), 200


@app.route("/api/employee/tasks", methods=["GET"])
@login_required
@role_required("employee")
def api_get_employee_tasks():
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Employee profile not found"}), 404
    tasks = db.get_tasks_by_employee(emp["employee_id"])
    return jsonify({"success": True, "data": tasks}), 200


@app.route("/api/manager/tasks", methods=["GET"])
@login_required
@role_required("manager", "hr")
def api_get_manager_tasks():
    tasks = db.get_tasks_by_manager(session["user_id"])
    return jsonify({"success": True, "data": tasks}), 200


@app.route("/api/tasks/<int:task_id>", methods=["GET"])
@login_required
def api_get_task_detail(task_id):
    task = db.get_task_by_id(task_id)
    if not task:
        return jsonify({"success": False, "message": "Task not found."}), 404
    return jsonify({"success": True, "data": task}), 200


@app.route("/api/tasks/<int:task_id>/result", methods=["PUT"])
@login_required
@role_required("employee")
def api_submit_task_result(task_id):
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Employee profile not found"}), 404

    data = request.get_json() or {}
    status = data.get("status", "COMPLETED").upper()
    employee_result = data.get("employee_result", "").strip() or None
    employee_reason = data.get("employee_reason", "").strip() or None

    if status not in ("PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"):
        return jsonify({"success": False, "message": "Invalid task status."}), 422

    db.submit_task_result(task_id, emp["employee_id"], status, employee_result, employee_reason)
    return jsonify({"success": True, "message": "Task progress and deliverables updated."}), 200


@app.route("/api/tasks/<int:task_id>/review", methods=["POST"])
@login_required
@role_required("manager", "hr")
def api_review_task(task_id):
    data = request.get_json() or {}
    rating = data.get("rating")
    comments = data.get("comments", "").strip() or None

    if rating is None:
        return jsonify({"success": False, "message": "Rating is required (1.00 to 5.00)."}), 422

    try:
        rating_val = float(rating)
        if rating_val < 1.00 or rating_val > 5.00:
            return jsonify({"success": False, "message": "Rating must be between 1.00 and 5.00."}), 422
    except ValueError:
        return jsonify({"success": False, "message": "Rating must be a numeric value."}), 422

    task = db.get_task_by_id(task_id)
    if not task:
        return jsonify({"success": False, "message": "Task not found."}), 404

    db.review_task(task_id, session["user_id"], rating_val, comments)
    return jsonify({"success": True, "message": f"Task rating recorded ({rating_val:.2f}/5.00)."}), 200


@app.route("/api/employee/task-average", methods=["GET"])
@login_required
def api_get_task_average():
    employee_id = request.args.get("employee_id")
    if not employee_id:
        emp = db.get_employee_by_user_id(session["user_id"])
        if not emp:
            return jsonify({"success": False, "message": "Employee record not found."}), 404
        employee_id = emp["employee_id"]
    else:
        try:
            employee_id = int(employee_id)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid employee ID."}), 422

    avg_rating, total_reviews = db.calculate_task_average(employee_id)
    return jsonify({
        "success": True,
        "employee_id": employee_id,
        "task_average": avg_rating,
        "total_reviews": total_reviews
    }), 200


# ============================================================
# REST APIS: PROMOTION WORKFLOW & ELIGIBILITY
# ============================================================

@app.route("/api/employee/promotion-eligibility", methods=["GET"])
@login_required
def api_get_promotion_eligibility():
    employee_id = request.args.get("employee_id")
    if not employee_id:
        emp = db.get_employee_by_user_id(session["user_id"])
        if not emp:
            return jsonify({"success": False, "message": "Employee record not found."}), 404
        employee_id = emp["employee_id"]
    else:
        try:
            employee_id = int(employee_id)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid employee ID."}), 422

    eligibility = db.check_promotion_eligibility(employee_id)
    return jsonify({"success": True, "data": eligibility}), 200


@app.route("/api/promotion-requests", methods=["POST"])
@login_required
@role_required("employee")
def api_create_promotion_request():
    emp = db.get_employee_by_user_id(session["user_id"])
    if not emp:
        return jsonify({"success": False, "message": "Employee record not found."}), 404

    data = request.get_json() or {}
    reason = data.get("reason", "").strip()
    appraisal_id = data.get("appraisal_id") or None
    document_reference = data.get("document_reference", "").strip() or None

    if not reason:
        return jsonify({"success": False, "message": "Promotion reason and justification are required."}), 422

    # Authoritative server-side evaluation of promotion eligibility
    eligibility = db.check_promotion_eligibility(emp["employee_id"])

    request_id = db.create_promotion_request(
        employee_id=emp["employee_id"],
        appraisal_id=appraisal_id,
        manager_id=emp.get("manager_id"),
        reason=reason,
        document_reference=document_reference,
        task_average=eligibility["task_average"]
    )

    return jsonify({
        "success": True,
        "message": "Promotion request submitted successfully.",
        "data": {
            "request_id": request_id,
            "eligibility": eligibility
        }
    }), 201


@app.route("/api/hr/promotion-requests", methods=["GET"])
@login_required
@role_required("hr", "administrator")
def api_get_hr_promotion_requests():
    status = request.args.get("status")
    requests_list = db.get_promotion_requests_for_hr(status=status)
    return jsonify({"success": True, "data": requests_list}), 200


@app.route("/api/promotion-requests/<int:request_id>", methods=["GET"])
@login_required
def api_get_promotion_request_detail(request_id):
    req = db.get_promotion_request_by_id(request_id)
    if not req:
        return jsonify({"success": False, "message": "Promotion request not found."}), 404
    return jsonify({"success": True, "data": req}), 200


@app.route("/api/promotion-requests/<int:request_id>/reject", methods=["POST"])
@login_required
@role_required("hr", "administrator")
def api_reject_promotion(request_id):
    data = request.get_json() or {}
    hr_response = data.get("response", "").strip() or None

    req = db.get_promotion_request_by_id(request_id)
    if not req:
        return jsonify({"success": False, "message": "Promotion request not found."}), 404

    db.reject_promotion_request(request_id, session["user_id"], hr_response)
    return jsonify({"success": True, "message": "Promotion request rejected."}), 200


@app.route("/api/promotion-requests/<int:request_id>/approve", methods=["POST"])
@login_required
@role_required("hr", "administrator")
def api_approve_promotion(request_id):
    data = request.get_json() or {}
    hr_response = data.get("response", "").strip() or "Promotion approved on performance merit."
    new_designation = data.get("new_designation", "").strip() or None

    req = db.get_promotion_request_by_id(request_id)
    if not req:
        return jsonify({"success": False, "message": "Promotion request not found."}), 404

    # Generate secure 12-character temporary password
    temp_password = secrets.token_urlsafe(12)
    temp_pwd_hash = generate_password_hash(temp_password)

    try:
        result = db.approve_promotion_transaction(
            request_id=request_id,
            hr_user_id=session["user_id"],
            temp_password_hash=temp_pwd_hash,
            hr_response=hr_response,
            new_designation=new_designation
        )

        # Dispatch official promotion email via SMTP
        email_service.send_promotion_email(
            to_address=result["email"],
            employee_name=result["name"],
            new_role=result["new_role"],
            new_designation=result["new_designation"],
            temp_password=temp_password,
            task_average=result["task_average"]
        )

        return jsonify({
            "success": True,
            "message": f"Promotion approved successfully for {result['name']}. Role upgraded to {result['new_role']}.",
            "data": {
                "user_id": result["user_id"],
                "employee_id": result["employee_id"],
                "email": result["email"],
                "name": result["name"],
                "new_role": result["new_role"],
                "new_designation": result["new_designation"],
                "task_average": result["task_average"]
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Promotion approval failed: {str(e)}"}), 500


@app.route("/api/promotions/history", methods=["GET"])
@login_required
def api_get_promotions_history():
    employee_id = request.args.get("employee_id")
    if employee_id:
        try:
            employee_id = int(employee_id)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid employee ID."}), 422

    history = db.get_promotions_history(employee_id=employee_id)
    return jsonify({"success": True, "data": history}), 200


@app.route("/api/appraisals/<int:appraisal_id>/full", methods=["GET"])
@login_required
@role_required("hr", "manager", "administrator")
def api_get_full_appraisal(appraisal_id):
    """
    Returns complete appraisal data package:
    appraisal metrics, self-review, manager review, documents, project tasks, and claims.
    """
    appraisal = db.get_appraisal_by_id(appraisal_id)
    if not appraisal:
        return jsonify({"success": False, "message": "Appraisal not found."}), 404

    employee_id = appraisal["employee_id"]
    documents = db.get_documents_by_employee(employee_id)
    tasks = db.get_tasks_by_employee(employee_id)
    claims = db.get_claims_by_employee(employee_id)
    task_avg, review_count = db.calculate_task_average(employee_id)
    eligibility = db.check_promotion_eligibility(employee_id)

    return jsonify({
        "success": True,
        "data": {
            "appraisal": appraisal,
            "documents": documents,
            "tasks": tasks,
            "claims": claims,
            "performance_task_average": task_avg,
            "total_task_reviews": review_count,
            "promotion_eligibility": eligibility
        }
    }), 200


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "Resource not found"}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "An internal server error occurred"}), 500
    return render_template("500.html"), 500


# ============================================================
# APPLICATION ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    try:
        print(f"[DATABASE] Using MySQL host={Config.DB_HOST}, port={Config.DB_PORT}, database={Config.DB_NAME}, user={Config.DB_USER}")
        db.init_db()
        db.seed_db()
    except Exception as e:
        print(f"[STARTUP WARNING] Database initialization check: {e}")

    port = int(os.getenv("PORT", 5000))
    debug = Config.DEBUG
    print(f"Starting Employee Appraisal Management System (EAMS) on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=debug)
