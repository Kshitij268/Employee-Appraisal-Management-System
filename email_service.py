"""
Employee Appraisal Management System (EAMS)
Email & Notification Service
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import Config, load_dotenv


def get_smtp_config():
    """Dynamically load and return current SMTP configurations from .env/Config."""
    load_dotenv(override=True)
    host = os.getenv("SMTP_HOST", getattr(Config, "SMTP_HOST", "smtp.gmail.com")).strip()
    port = int(os.getenv("SMTP_PORT", getattr(Config, "SMTP_PORT", 587)))
    username = os.getenv("SMTP_USERNAME", getattr(Config, "SMTP_USERNAME", "")).strip()
    password = os.getenv("SMTP_PASSWORD", getattr(Config, "SMTP_PASSWORD", "")).strip().replace(" ", "")
    from_address = os.getenv("SMTP_FROM", getattr(Config, "SMTP_FROM", username)).strip() or username
    bypass_debug = os.getenv("OTP_BYPASS_DEBUG", str(getattr(Config, "OTP_BYPASS_DEBUG", "True"))).lower() in ("true", "1", "yes")

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_address": from_address,
        "bypass_debug": bypass_debug,
        "is_configured": bool(username and password)
    }


def is_smtp_configured():
    """Check if SMTP username and password are provided."""
    cfg = get_smtp_config()
    return cfg["is_configured"]


def send_email(to_address, subject, body_html, body_text=None):
    """
    Send an email via SMTP.
    Returns (success: bool, error: str or None).
    Never raises an uncaught exception.
    """
    cfg = get_smtp_config()
    host = cfg["host"]
    port = cfg["port"]
    username = cfg["username"]
    password = cfg["password"]
    from_address = cfg["from_address"] or username or "no-reply@eams.local"

    # If SMTP credentials are missing, log clearly so user knows what to configure
    if not cfg["is_configured"]:
        print("\n" + "=" * 70)
        print("[EMAIL NOTICE] SMTP credentials are not configured in .env!")
        print("To send actual emails to Gmail:")
        print("  1. In .env, set: SMTP_USERNAME=your_gmail@gmail.com")
        print("  2. Generate a 16-character Google App Password at: https://myaccount.google.com/apppasswords")
        print("  3. In .env, set: SMTP_PASSWORD=your_16_char_app_password")
        print("-" * 70)
        print(f"Destination: {to_address}")
        print(f"Subject: {subject}")
        print(f"Content:\n{body_text or body_html}")
        print("=" * 70 + "\n")
        return True, None

    try:
        # Prepare MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = to_address

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        if port == 465:
            # SSL Connection
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(username, password)
                server.sendmail(from_address, [to_address], msg.as_string())
        else:
            # TLS Connection (port 587 standard)
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
                server.sendmail(from_address, [to_address], msg.as_string())

        print(f"\n[SMTP SUCCESS] Email successfully delivered to {to_address} (via {username})")
        return True, None
    except smtplib.SMTPAuthenticationError as auth_err:
        err_msg = (
            f"Gmail SMTP Authentication failed. If using Gmail, you MUST use an 'App Password' "
            f"(16 letters generated from https://myaccount.google.com/apppasswords), "
            f"not your regular Gmail password. Error: {auth_err}"
        )
        print(f"\n[SMTP ERROR] {err_msg}")
        return False, err_msg
    except Exception as e:
        err_msg = f"Failed to deliver email to {to_address}: {e}"
        print(f"\n[SMTP ERROR] {err_msg}")
        return False, err_msg


def send_otp_email(to_address, otp_code):
    """Send 4-digit OTP code to employee."""
    subject = "[EAMS] Your Login Verification Code"
    body_text = f"Your login verification code is: {otp_code}\n\nThis code is valid for 2 minutes. Do not share it with anyone."
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #333; margin-top: 0;">Login Verification Code</h2>
        <p style="color: #666; font-size: 15px;">Use the following 4-digit code to complete your login to the Employee Appraisal Management System:</p>
        <div style="background-color: #f4f6f9; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #2b5797;">{otp_code}</span>
        </div>
        <p style="color: #888; font-size: 13px;">This code is valid for <strong>2 minutes</strong>. If you did not request this code, please secure your account immediately.</p>
    </div>
    """
    return send_email(to_address, subject, body_html, body_text)


def send_promotion_email(to_address, employee_name, new_role, new_designation, temp_password, task_average):
    """Send official promotion notification email with temporary password."""
    subject = "[EAMS] Official Promotion Notification & Account Upgrade"
    body_text = f"""
Congratulations {employee_name}!

We are pleased to inform you that your promotion has been officially approved.
New Role: {new_role}
New Designation: {new_designation}
Performance Task Average: {task_average:.2f} / 5.00

Your account credentials have been updated. Please log in with your temporary password:
Temporary Password: {temp_password}

IMPORTANT: You will be required to change this temporary password immediately upon your next login.
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 550px; margin: 0 auto; padding: 25px; border: 1px solid #d4edda; border-radius: 8px; background-color: #ffffff;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #28a745; margin: 0;">🎉 Congratulations, {employee_name}!</h2>
            <p style="color: #555; font-size: 15px; margin-top: 5px;">Your promotion has been officially approved.</p>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <tr>
                <td style="padding: 8px 12px; font-weight: bold; color: #495057; background: #f8f9fa; border: 1px solid #e9ecef;">New Role</td>
                <td style="padding: 8px 12px; color: #212529; border: 1px solid #e9ecef;"><strong>{new_role.upper()}</strong></td>
            </tr>
            <tr>
                <td style="padding: 8px 12px; font-weight: bold; color: #495057; background: #f8f9fa; border: 1px solid #e9ecef;">New Designation</td>
                <td style="padding: 8px 12px; color: #212529; border: 1px solid #e9ecef;">{new_designation}</td>
            </tr>
            <tr>
                <td style="padding: 8px 12px; font-weight: bold; color: #495057; background: #f8f9fa; border: 1px solid #e9ecef;">Task Rating Average</td>
                <td style="padding: 8px 12px; color: #212529; border: 1px solid #e9ecef;">{task_average:.2f} / 5.00</td>
            </tr>
        </table>

        <div style="background-color: #fff3cd; border: 1px solid #ffeeba; border-radius: 6px; padding: 15px; margin-bottom: 20px;">
            <p style="margin: 0 0 8px 0; color: #856404; font-weight: bold;">New Login Credentials</p>
            <p style="margin: 0; color: #856404; font-size: 14px;">Your account role has been updated. Use this temporary password to log in:</p>
            <div style="text-align: center; margin-top: 10px;">
                <code style="font-size: 18px; background: #ffffff; padding: 6px 14px; border-radius: 4px; border: 1px solid #eedc9e; font-weight: bold; color: #333;">{temp_password}</code>
            </div>
        </div>

        <p style="color: #721c24; font-size: 13px; margin: 0; font-weight: bold;">
            * Security Notice: You are required to change this temporary password immediately upon your next login.
        </p>
    </div>
    """
    return send_email(to_address, subject, body_html, body_text)
