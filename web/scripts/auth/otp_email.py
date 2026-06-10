"""Send OTP emails via Gmail SMTP."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
APP_NAME = "Shikhbo (শিখবো)"


def send_otp(to_email: str, otp_code: str, purpose: str = "reset") -> bool:
    """Returns True on success, False on failure."""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[mail] MAIL_USERNAME/MAIL_PASSWORD not set — skipping email send")
        return False

    subject = f"{APP_NAME} — Your verification code"
    action = "reset your password" if purpose == "reset" else "verify your account"

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="background:#141619;color:#f0f0f0;font-family:'Segoe UI',Arial,sans-serif;padding:40px 20px;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#1e2126;border-radius:12px;padding:36px;border:1px solid rgba(255,255,255,0.1);">
    <div style="font-size:28px;font-weight:700;margin-bottom:8px;">⬡ Shikhbo</div>
    <p style="color:#b0b0b0;margin-bottom:28px;font-size:14px;">Your AI Study Partner</p>
    <h2 style="font-size:20px;margin-bottom:16px;">Verification Code</h2>
    <p style="color:#b0b0b0;margin-bottom:24px;">Use this code to {action}. It expires in <strong style="color:#f0f0f0;">10 minutes</strong>.</p>
    <div style="background:#303841;border-radius:8px;padding:20px;text-align:center;margin-bottom:24px;">
      <span style="font-size:36px;font-weight:700;letter-spacing:10px;color:#ffffff;">{otp_code}</span>
    </div>
    <p style="color:#6a6a6a;font-size:13px;">If you didn't request this, you can safely ignore this email.</p>
  </div>
</body>
</html>
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{APP_NAME} <{MAIL_USERNAME}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_USERNAME, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[mail] Failed to send OTP to {to_email}: {e}")
        return False
