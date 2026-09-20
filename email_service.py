"""
Email Service Module (SMTP & IMAP)
Allows the bot to connect directly to any email provider (Gmail, Outlook, Yahoo)
to read incoming emails and send rich replies with charts and CSV attachments.
"""
import os
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
        
        attachments format:
        [
            {'type': 'image', 'data': bytes, 'filename': 'aapl_chart.png'},
            {'type': 'csv', 'data': str/bytes, 'filename': 'aapl_data.csv'}
        ]
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
            is_html = "<html" in message.lower() or "<div" in message.lower() or "<b" in message.lower()
            if is_html:
                # Attach HTML version
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

                    # If string (like CSV), encode to bytes
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

            # Connect and send via SMTP
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.send_message(msg)

            logger.info(f"Successfully sent email to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
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

            # Search for unread emails
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
                        # Parse sender email address
                        from_email = email.utils.parseaddr(from_header)[1]

                        # Extract subject
                        subject, encoding = decode_header(msg.get("Subject", ""))[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="ignore")

                        # Extract body text
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    charset = part.get_content_charset() or "utf-8"
                                    body = part.get_payload(decode=True).decode(charset, errors="ignore")
                                    break
                        else:
                            charset = msg.get_content_charset() or "utf-8"
                            body = msg.get_payload(decode=True).decode(charset, errors="ignore")

                        logger.info(f"Processing inbound email from {from_email}: '{subject}'")

                        # Pass to the bot handler
                        handler_callback(from_email, f"{subject} {body}".strip())

            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"Error checking email inbox: {e}")
