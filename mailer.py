import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# SMTP CONFIGURATION
SMTP_SERVER   = "smtp.gmail.com"
SMTP_PORT     = 465
SMTP_USER     = "vendor_aayush@letzryd.com"
SMTP_PASSWORD = "gqnk qlhy rdcl rwrn".replace(" ", "")  # Google App Password
DEFAULT_RECIPIENTS = ["vendor_aayush@letzryd.com"]


def send_success_email(
    date_window: str,
    blr_rows: int,
    mum_rows: int,
    hyd_rows: int,
    total_rows: int,
    duration_str: str,
    blr_file_url: str = "#",
    mum_file_url: str = "#",
    hyd_file_url: str = "#",
    master_file_url: str = "#",
    recipients: list[str] = None
) -> bool:
    """
    Sends LetzRyd branded Green Success Email with cloud bucket download links for all 3 cities & Master report.
    No heavy attachments - all files downloadable via GCS links.
    """
    if recipients is None:
        recipients = DEFAULT_RECIPIENTS

    msg = MIMEMultipart("alternative")
    subject = f"✅ [SUCCESS] LetzRyd Uber Statement Ingested ({date_window})"
    msg["Subject"] = subject
    msg["From"] = f"LetzRyd Uber Automation <{SMTP_USER}>"
    msg["To"] = ", ".join(recipients)

    now_ist = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background-color: #f4f6f8;
    margin: 0;
    padding: 20px;
  }}
  .container {{
    max-width: 600px;
    margin: 0 auto;
    background: #ffffff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
    border: 1px solid #e5e7eb;
  }}
  .header {{
    text-align: center;
    padding: 28px 20px 15px;
    background: #ffffff;
  }}
  .brand {{
    font-size: 24px;
    font-weight: 800;
    color: #0b4f2c;
    letter-spacing: 1px;
  }}
  .brand-sub {{
    font-size: 11px;
    font-weight: 700;
    color: #6b7280;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-top: 4px;
  }}
  .content {{
    padding: 10px 35px 30px;
  }}
  .badge {{
    display: inline-block;
    background: #10b981;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  h2 {{
    font-size: 19px;
    color: #111827;
    margin: 14px 0 6px;
    font-weight: 700;
  }}
  .subtitle {{
    font-size: 13px;
    color: #4b5563;
    margin-bottom: 22px;
  }}
  .summary-card {{
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 24px;
  }}
  .val-badge {{
    background: #d1fae5;
    color: #065f46;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 12px;
  }}
  .downloads-card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 25px;
  }}
  .dl-title {{
    font-size: 13px;
    font-weight: 700;
    color: #334155;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .dl-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #f1f5f9;
  }}
  .dl-row:last-child {{
    border-bottom: none;
  }}
  .dl-link {{
    color: #047857;
    text-decoration: none;
    font-weight: 700;
    font-size: 12px;
    background: #e6f4ea;
    padding: 4px 10px;
    border-radius: 6px;
  }}
  .dl-link:hover {{
    background: #cbf0d7;
  }}
  .btn-master {{
    display: block;
    background: #047857;
    color: #ffffff !important;
    text-decoration: none;
    text-align: center;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 20px;
    border-radius: 8px;
    margin: 15px 0 5px;
    box-shadow: 0 2px 6px rgba(4,120,87,0.25);
  }}
  .footer {{
    background: #f9fafb;
    padding: 20px;
    text-align: center;
    border-top: 1px solid #e5e7eb;
    font-size: 11px;
    color: #6b7280;
  }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">🚕 LETZRYD</div>
      <div class="brand-sub">FLEET FINANCIAL OPERATIONS • UBER PIPELINE</div>
    </div>
    <div class="content">
      <span class="badge">STATUS: SUCCESSFUL</span>
      <h2>Uber Statement Ingestion Completed</h2>
      <div class="subtitle">All ride and incentive ledger records successfully loaded into PostgreSQL and Cloud Storage.</div>
      
      <div class="summary-card">
        <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
          <tr style="border-bottom: 1px dashed #dcfce7;">
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Target Date Window:</td>
            <td style="padding: 7px 0; color: #111827; font-weight: 700; text-align: right;">{date_window}</td>
          </tr>
          <tr style="border-bottom: 1px dashed #dcfce7;">
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Bangalore Ingested:</td>
            <td style="padding: 7px 0; color: #111827; font-weight: 700; text-align: right;">{blr_rows:,} records</td>
          </tr>
          <tr style="border-bottom: 1px dashed #dcfce7;">
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Mumbai Ingested:</td>
            <td style="padding: 7px 0; color: #111827; font-weight: 700; text-align: right;">{mum_rows:,} records</td>
          </tr>
          <tr style="border-bottom: 1px dashed #dcfce7;">
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Hyderabad Ingested:</td>
            <td style="padding: 7px 0; color: #111827; font-weight: 700; text-align: right;">{hyd_rows:,} records</td>
          </tr>
          <tr style="border-bottom: 1px dashed #dcfce7;">
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Total Master Records:</td>
            <td style="padding: 7px 0; color: #047857; font-weight: 800; text-align: right;">{total_rows:,} rows</td>
          </tr>
          <tr style="border-bottom: 1px dashed #dcfce7;">
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Execution Duration:</td>
            <td style="padding: 7px 0; color: #111827; font-weight: 700; text-align: right;">{duration_str}</td>
          </tr>
          <tr>
            <td style="padding: 7px 0; color: #4b5563; font-weight: 500;">Database Status:</td>
            <td style="padding: 7px 0; text-align: right;"><span class="val-badge">ACTIVE & COMMITTED</span></td>
          </tr>
        </table>
      </div>

      <div class="downloads-card">
        <div class="dl-title">📂 Cloud Storage Statements (.xlsx)</div>
        <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 6px 0; color: #334155; font-weight: 600;">Bangalore Fleet</td>
            <td style="padding: 6px 0; text-align: right;"><a href="{blr_file_url}" class="dl-link">Download .xlsx</a></td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 6px 0; color: #334155; font-weight: 600;">Mumbai Fleet</td>
            <td style="padding: 6px 0; text-align: right;"><a href="{mum_file_url}" class="dl-link">Download .xlsx</a></td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 6px 0; color: #334155; font-weight: 600;">Hyderabad Fleet</td>
            <td style="padding: 6px 0; text-align: right;"><a href="{hyd_file_url}" class="dl-link">Download .xlsx</a></td>
          </tr>
        </table>
        
        <a href="{master_file_url}" class="btn-master">📥 Download Combined Master Statement (.xlsx)</a>
      </div>
    </div>
    
    <div class="footer">
      <strong>LetzRyd Mobility Private Limited</strong><br>
      Automated Cloud Pipeline • Serverless Cloud Run (asia-south1)<br>
      Execution Timestamp: {now_ist} • Confidential
    </div>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
        print(f"✅ Success email sent to {recipients}", flush=True)
        return True
    except Exception as e:
        print(f"[-] Email send error: {e}", flush=True)
        return False


def send_failure_email(
    date_window: str,
    failure_reason: str,
    attempts_count: int = 4,
    recipients: list[str] = None
) -> bool:
    """
    Sends LetzRyd Red Failure Alert Email matching fleet operations standard template.
    Only triggered after the 4th (final) attempt fails.
    """
    if recipients is None:
        recipients = DEFAULT_RECIPIENTS

    msg = MIMEMultipart("alternative")
    subject = f"⚠️ [ALERT] LetzRyd Uber Ingestion Failed ({date_window})"
    msg["Subject"] = subject
    msg["From"] = f"LetzRyd Uber Automation <{SMTP_USER}>"
    msg["To"] = ", ".join(recipients)

    now_ist = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background-color: #f4f6f8;
    margin: 0;
    padding: 20px;
  }}
  .container {{
    max-width: 600px;
    margin: 0 auto;
    background: #ffffff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
    border: 1px solid #e5e7eb;
  }}
  .header {{
    text-align: center;
    padding: 28px 20px 15px;
    background: #ffffff;
  }}
  .brand {{
    font-size: 24px;
    font-weight: 800;
    color: #0b4f2c;
    letter-spacing: 1px;
  }}
  .brand-sub {{
    font-size: 11px;
    font-weight: 700;
    color: #6b7280;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-top: 4px;
  }}
  .content {{
    padding: 10px 35px 30px;
  }}
  .badge-red {{
    display: inline-block;
    background: #ef4444;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  h2 {{
    font-size: 19px;
    color: #111827;
    margin: 14px 0 6px;
    font-weight: 700;
  }}
  .subtitle {{
    font-size: 13px;
    color: #4b5563;
    margin-bottom: 22px;
  }}
  .summary-card-red {{
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-left: 4px solid #ef4444;
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 26px;
  }}
  .val-green {{
    background: #d1fae5;
    color: #065f46;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 12px;
  }}
  .footer {{
    background: #f9fafb;
    padding: 20px;
    text-align: center;
    border-top: 1px solid #e5e7eb;
    font-size: 11px;
    color: #6b7280;
  }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">🚕 LETZRYD</div>
      <div class="brand-sub">FLEET FINANCIAL OPERATIONS • UBER PIPELINE</div>
    </div>
    <div class="content">
      <span class="badge-red">STATUS: ACTION REQUIRED</span>
      <h2>Uber Statement Ingestion Incomplete</h2>
      <div class="subtitle">The automated pipeline was unable to secure statements from Uber after all {attempts_count} scheduled retry attempts.</div>
      
      <div class="summary-card-red">
        <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
          <tr style="border-bottom: 1px dashed #fee2e2;">
            <td style="padding: 9px 0; color: #4b5563; font-weight: 500; width: 35%;">Target Date Window:</td>
            <td style="padding: 9px 0; color: #111827; font-weight: 700;">{date_window}</td>
          </tr>
          <tr style="border-bottom: 1px dashed #fee2e2;">
            <td style="padding: 9px 0; color: #4b5563; font-weight: 500; vertical-align: top;">Failure Reason:</td>
            <td style="padding: 9px 0; color: #b91c1c; font-weight: 600; line-height: 1.4;">{failure_reason}</td>
          </tr>
          <tr style="border-bottom: 1px dashed #fee2e2;">
            <td style="padding: 9px 0; color: #4b5563; font-weight: 500;">Database Protection:</td>
            <td style="padding: 9px 0;"><span class="val-green">SAFE & UNTOUCHED</span></td>
          </tr>
          <tr>
            <td style="padding: 9px 0; color: #4b5563; font-weight: 500; vertical-align: top;">Recovery Action:</td>
            <td style="padding: 9px 0; color: #374151; font-weight: 500; line-height: 1.4;">Self-healing cumulative backfill will run automatically on the next scheduled trigger.</td>
          </tr>
        </table>
      </div>
    </div>
    
    <div class="footer">
      <strong>LetzRyd Mobility Private Limited</strong><br>
      Automated Cloud Pipeline • Serverless Microservice (asia-south1)<br>
      Execution Timestamp: {now_ist} • Confidential
    </div>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
        print(f"✅ Failure alert email sent to {recipients}", flush=True)
        return True
    except Exception as e:
        print(f"[-] Alert email error: {e}", flush=True)
        return False
