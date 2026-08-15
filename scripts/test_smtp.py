#!/usr/bin/env python3
"""
Standalone SMTP Email Configuration Diagnostic and Test Script for EduMi.
Tests SMTP connection, STARTTLS / SSL handshake, authentication, and email delivery.

Usage:
    python scripts/test_smtp.py [recipient@example.com]
    python scripts/test_smtp.py scarycrimson629@gmail.com --verbose
"""
import sys
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid

# ==============================================================================
# SMTP CONFIGURATION (Gmail Configuration — Verified & Operational)
# ==============================================================================
SMTP_HOST         = "smtp.gmail.com"
SMTP_PORT         = 587
SMTP_USE_TLS      = True
SMTP_USE_SSL      = False
SMTP_USER         = "your_email@gmail.com"
SMTP_PASSWORD     = "your_app_specific_password_here"
FROM_EMAIL        = "EduMi Support <your_email@gmail.com>"
DEFAULT_RECIPIENT = "example_email@gmail.com"   # <-- Jisko email bhejni hai uska address yahan likhein
# ==============================================================================


def print_banner(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step_num, title):
    print(f"\n[Step {step_num}] {title}...")


def main():
    parser = argparse.ArgumentParser(description="Test SMTP configuration and dispatch a test email.")
    parser.add_argument(
        'recipient',
        nargs='?',
        default=None,
        help="Target email address to receive the test email (defaults to SMTP_USER if omitted)."
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        default=True,
        help="Show detailed SMTP dialogue protocol exchange (default: True)."
    )
    args = parser.parse_args()

    recipient = args.recipient or DEFAULT_RECIPIENT or SMTP_USER

    print_banner("EduMi 2.0 — SMTP Configuration & Diagnostic Tool")
    print(f"• Mode             : Standalone (Isolated from .env)")
    print(f"• SMTP Server Host : {SMTP_HOST}")
    print(f"• SMTP Port        : {SMTP_PORT}")
    print(f"• Security Mode    : {'SSL (Port 465)' if SMTP_USE_SSL else ('STARTTLS (Port 587)' if SMTP_USE_TLS else 'Plaintext (Port 25)')}")
    print(f"• Authenticated User: {SMTP_USER}")
    print(f"• Password Length  : {len(SMTP_PASSWORD)} characters ({'Configured' if SMTP_PASSWORD else 'EMPTY'})")
    print(f"• From Header      : {FROM_EMAIL}")
    print(f"• Recipient (To)   : {recipient}")
    print("=" * 70)

    # 1. Prepare Email Message
    print_step(1, "Building MIME email message")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'EduMi LMS — SMTP Test & Verification Diagnostics'
    msg['From'] = FROM_EMAIL
    msg['To'] = recipient
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='edumi.local')

    text_body = f"""
Hello,

This is a diagnostic test email sent by the EduMi SMTP testing tool.

Configuration Summary:
- SMTP Host: {SMTP_HOST}:{SMTP_PORT}
- Sent to: {recipient}
- Timestamp: {msg['Date']}

Your SMTP email verification and 6-digit OTP delivery system is working properly!

Best regards,
EduMi Support Team
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px;">
    <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 10px; overflow: hidden; border: 1px solid #e5e7eb; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
        <div style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 24px; text-align: center; color: #ffffff;">
            <h1 style="margin: 0; font-size: 22px; font-weight: 700;">EduMi LMS — SMTP Diagnostic Test</h1>
            <p style="margin: 6px 0 0 0; font-size: 14px; opacity: 0.9;">Email Delivery Verification</p>
        </div>
        <div style="padding: 28px 24px; color: #374151; font-size: 15px; line-height: 1.6;">
            <p><strong>Hello!</strong></p>
            <p>If you are receiving this message, your <strong>SMTP configuration for EduMi is fully operational</strong>.</p>
            
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #166534; font-size: 16px;">Test Status: SUCCESS</h3>
                <ul style="margin: 8px 0 0 0; padding-left: 20px; font-size: 13px; color: #15803d;">
                    <li><strong>SMTP Host:</strong> {SMTP_HOST}:{SMTP_PORT}</li>
                    <li><strong>Auth User:</strong> {SMTP_USER}</li>
                    <li><strong>Recipient:</strong> {recipient}</li>
                </ul>
            </div>
            
            <p style="font-size: 13px; color: #6b7280; margin-bottom: 0;">
                This test verifies that user registration emails, OTP codes, and password reset notifications will be delivered smoothly.
            </p>
        </div>
        <div style="background: #f9fafb; border-top: 1px solid #e5e7eb; padding: 16px 24px; font-size: 12px; color: #9ca3af; text-align: center;">
            &copy; 2026 EduMi Learning Platform. Diagnostic Tool.
        </div>
    </div>
</body>
</html>
"""

    msg.attach(MIMEText(text_body.strip(), 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body.strip(), 'html', 'utf-8'))
    print("✓ Email payload generated successfully.")

    # 2. Establish Connection
    server = None
    try:
        if SMTP_USE_SSL:
            print_step(2, f"Connecting via SSL to {SMTP_HOST}:{SMTP_PORT}")
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            print_step(2, f"Connecting to {SMTP_HOST}:{SMTP_PORT}")
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)

        if args.verbose:
            server.set_debuglevel(1)

        print("✓ Connected to SMTP server.")

        # 3. Handshake & STARTTLS
        print_step(3, "Performing EHLO greeting and TLS negotiation")
        server.ehlo()

        if SMTP_USE_TLS and not SMTP_USE_SSL:
            if server.has_extn('STARTTLS'):
                print("• Server supports STARTTLS. Starting TLS encryption...")
                server.starttls()
                server.ehlo()
                print("✓ TLS session active and secured.")
            else:
                print("! Warning: Server does not support STARTTLS.")

        # 4. Authentication
        if SMTP_USER and SMTP_PASSWORD:
            print_step(4, f"Authenticating as {SMTP_USER}")
            server.login(SMTP_USER, SMTP_PASSWORD)
            print("✓ SMTP Authentication successful!")
        else:
            print_step(4, "Skipping authentication (no credentials provided)")

        # 5. Dispatch
        print_step(5, f"Dispatching test email to {recipient}")
        server.send_message(msg)
        print("✓ Email dispatched successfully by SMTP server!")

        print_banner("SUCCESS! Test email sent successfully.")
        print(f"Please check the inbox (and spam folder) of: {recipient}\n")

    except smtplib.SMTPAuthenticationError as e:
        print("\n" + "!" * 70)
        print("AUTHENTICATION FAILED (SMTPAuthenticationError)")
        print("!" * 70)
        print(f"Error Code: {e.smtp_code}")
        print(f"Error Message: {e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else e.smtp_error}")
        print("\nTroubleshooting Tips:")
        print("1. For Gmail: Make sure you are using a 16-character App Password (not your normal Google password).")
        print("2. Verify 2-Step Verification is enabled on the Google Account.")
        print("3. Check for typos in EMAIL_HOST_USER or EMAIL_HOST_PASSWORD in your .env file.")
        sys.exit(1)

    except (smtplib.SMTPConnectError, TimeoutError, OSError) as e:
        print("\n" + "!" * 70)
        print("CONNECTION FAILED")
        print("!" * 70)
        print(f"Error: {e}")
        print("\nTroubleshooting Tips:")
        print("1. Ensure this machine has an active internet connection.")
        print(f"2. Verify outbound TCP traffic on port {SMTP_PORT} is not blocked by local firewall or ISP.")
        print(f"3. Test DNS resolution for '{SMTP_HOST}'.")
        sys.exit(1)

    except Exception as e:
        print("\n" + "!" * 70)
        print("UNEXPECTED ERROR")
        print("!" * 70)
        print(f"Error: {type(e).__name__}: {e}")
        sys.exit(1)

    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


if __name__ == '__main__':
    main()
