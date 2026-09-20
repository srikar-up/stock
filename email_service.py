"""
Email Service Module (SMTP & IMAP)
Allows the bot to connect directly to any email provider (Gmail, Outlook, Yahoo)
to read incoming emails and send rich replies with charts and CSV attachments.
Includes defensive cleaning to strip quoted replies, HTML tags, and email signatures.
"""
import os
import re
import time
import smtplib
import imaplib
import email
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import logging
from typing import List, Dict, Any, Optional, Callable
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("email_service")


def clean_email_text(raw_text: str) -> str:
    """
    Cleans raw email content:
    - Strips HTML tags
    - Removes quoted reply blocks (e.g. 'On ... wrote:', lines with '>')
    - Removes mobile signatures ('Sent from my...')
    """
    if not raw_text:
        return ""

    # Strip HTML tags
    text = re.sub(r"<style[\s\S]*?</style>", " ", raw_text, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    lines = []
    for line in text.splitlines():
        line_clean = line.strip()
        # Cut off quoted reply history
        if line_clean.startswith(">"):
            continue
        if re.search(r"^on\s+.*wrote:$", line_clean, flags=re.IGNORECASE):
            break
        if re.search(r"^-+\s*original message\s*-+", line_clean, flags=re.IGNORECASE):
            break
        if line_clean.lower().startswith("from:") and "@" in line_clean:
            break
        if line_clean.lower().startswith("sent from my "):
            continue

        lines.append(line_clean)

    cleaned = " ".join(lines)
    return " ".join(cleaned.split())


class EmailBotService:
    """
    Handles outbound SMTP sending and inbound IMAP inbox monitoring.
    """

    def __init__(self):
        self.email_address = os.environ.get("EMAIL_ADDRESS", "").strip()
        self.email_password = os.environ.get("EMAIL_PASSWORD", "").strip()
        self.smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", 587))
        self.imap_server = os.environ.get("IMAP_SERVER", "imap.gmail.com")
        self.imap_port = int(os.environ.get("IMAP_PORT", 993))

    def is_configured(self) -> bool:
        """Returns True if email credentials are set in .env."""
        return bool(self.email_address and self.email_password and "your_email" not in self.email_address)

    def send_email(
        self,
        to_email: str,
        subject: str,
        message: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Sends an email response via SMTP with optional image / CSV attachments.
        """
        if not self.is_configured():
            logger.warning("EMAIL_ADDRESS or EMAIL_PASSWORD not configured. Skipping SMTP send.")
            return False

        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = f"Stock Assistant 📈 <{self.email_address}>"
            msg["To"] = to_email
            msg["Subject"] = subject

            # Determine whether message is HTML or plain text
            is_html = "<html" in message.lower() or "<div" in message.lower() or "<b" in message.lower() or "<br" in message.lower()
            if is_html:
                html_part = MIMEText(message, "html", "utf-8")
                msg.attach(html_part)
            else:
                text_part = MIMEText(message, "plain", "utf-8")
                msg.attach(text_part)

            # Process attachments
            if attachments:
                for att in attachments:
                    att_type = att.get("type", "")
                    data = att.get("data")
                    filename = att.get("filename", "attachment")

                    if not data:
                        continue

                    if isinstance(data, str):
                        data_bytes = data.encode("utf-8")
                    else:
                        data_bytes = data

                    if att_type == "image":
                        part = MIMEBase("image", "png")
                    elif att_type == "csv":
                        part = MIMEBase("text", "csv")
                    else:
                        part = MIMEBase("application", "octet-stream")

                    part.set_payload(data_bytes)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                    msg.attach(part)

            # Connect and send via SMTP with timeout and SSL fallback
            logger.info(f"Connecting to SMTP {self.smtp_server}:{self.smtp_port} to send reply to {to_email}...")
            sent = False
            try:
                # Primary attempt: configured port (default 587 STARTTLS) with 12s timeout
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=12) as server:
                    server.starttls()
                    server.login(self.email_address, self.email_password)
                    server.send_message(msg)
                    sent = True
            except Exception as smtp_err:
                logger.warning(f"SMTP port {self.smtp_port} failed or timed out: {smtp_err}. Retrying via direct SSL (port 465)...")
                # Fallback attempt: port 465 SSL (bypasses ISP port 587 packet drops / STARTTLS stalls)
                with smtplib.SMTP_SSL(self.smtp_server, 465, timeout=15) as ssl_server:
                    ssl_server.login(self.email_address, self.email_password)
                    ssl_server.send_message(msg)
                    sent = True

            if sent:
                logger.info(f"✅ Successfully sent email reply to {to_email}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send email to {to_email}: {e}")
            return False

    def poll_inbox_and_respond(self, handler_callback: Callable[[str, str], None]):
        """
        Connects to IMAP inbox, looks for UNSEEN emails, processes them with handler_callback,
        and marks them as seen.
        """
        if not self.is_configured():
            logger.warning("Email credentials not configured in .env. Cannot poll inbox.")
            return

        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.email_password)
            mail.select("inbox")

            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                mail.close()
                mail.logout()
                return

            email_ids = messages[0].split()
            logger.info(f"Found {len(email_ids)} new unread email(s).")

            for eid in email_ids:
                res, data = mail.fetch(eid, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        # Extract sender email
                        from_header = msg.get("From", "")
                        from_email = email.utils.parseaddr(from_header)[1]

                        # Ignore self-sent emails (prevent infinite loop)
                        if from_email.lower() == self.email_address.lower():
                            logger.info("Skipping email sent from self.")
                            continue

                        # Extract subject
                        subject, encoding = decode_header(msg.get("Subject", ""))[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="ignore")

                        # Extract body text (prefer text/plain, fallback to text/html)
                        plain_body = ""
                        html_body = ""

                        if msg.is_multipart():
                            for part in msg.walk():
                                ctype = part.get_content_type()
                                cdisp = str(part.get("Content-Disposition"))
                                if "attachment" in cdisp:
                                    continue
                                charset = part.get_content_charset() or "utf-8"

                                if ctype == "text/plain" and not plain_body:
                                    plain_body = part.get_payload(decode=True).decode(charset, errors="ignore")
                                elif ctype == "text/html" and not html_body:
                                    html_body = part.get_payload(decode=True).decode(charset, errors="ignore")
                        else:
                            charset = msg.get_content_charset() or "utf-8"
                            raw = msg.get_payload(decode=True).decode(charset, errors="ignore")
                            if msg.get_content_type() == "text/html":
                                html_body = raw
                            else:
                                plain_body = raw

                        raw_content = plain_body if plain_body else html_body
                        cleaned_body = clean_email_text(raw_content)
                        cleaned_subject = clean_email_text(subject)

                        full_query = f"{cleaned_subject} {cleaned_body}".strip()

                        logger.info(f"📧 Processing cleaned email from {from_email}: '{full_query}'")
                        handler_callback(from_email, full_query)

            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"Error checking email inbox: {e}")
