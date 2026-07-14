from __future__ import annotations

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _split_addresses(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _bool_from_env(value: str | None, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def send_html_email(
    subject: str,
    html_body: str,
    text_body: str = "",
    attachment_path: Path | None = None,
) -> None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_use_tls = _bool_from_env(os.getenv("SMTP_USE_TLS"), True)
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    mail_from = os.getenv("MAIL_FROM", smtp_user).strip()
    mail_to = _split_addresses(os.getenv("MAIL_TO"))
    mail_cc = _split_addresses(os.getenv("MAIL_CC"))

    if not smtp_host:
        raise ValueError("SMTP_HOST 값이 없습니다.")
    if not smtp_user:
        raise ValueError("SMTP_USER 값이 없습니다.")
    if not smtp_password:
        raise ValueError("SMTP_PASSWORD 값이 없습니다.")
    if not mail_from:
        raise ValueError("MAIL_FROM 값이 없습니다.")
    if not mail_to:
        raise ValueError("MAIL_TO 값이 없습니다.")

    recipients = mail_to + mail_cc

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)
    if mail_cc:
        msg["Cc"] = ", ".join(mail_cc)

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(text_body or "HTML 이메일을 확인해 주세요.", "plain", "utf-8"))
    alternative.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alternative)

    if attachment_path and attachment_path.exists():
        part = MIMEApplication(attachment_path.read_bytes(), Name=attachment_path.name)
        part["Content-Disposition"] = f'attachment; filename="{attachment_path.name}"'
        msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(mail_from, recipients, msg.as_string())

    print(f"[정보] 이메일 발송 완료: {', '.join(recipients)}")
