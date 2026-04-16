import imaplib
import time


class IMAPAuthError(Exception):
    pass


def connect_imap(host: str, port: int, email: str, password: str, retries: int = 3) -> imaplib.IMAP4_SSL:
    last_error = None
    for attempt in range(retries):
        try:
            conn = imaplib.IMAP4_SSL(host, port)
            conn.login(email, password)
            return conn
        except imaplib.IMAP4.error as e:
            raise IMAPAuthError(
                f"Authentication failed for {email} at {host}. "
                f"Check your app password. Error: {e}"
            )
        except (OSError, TimeoutError) as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise IMAPAuthError(f"Connection to {host}:{port} failed after {retries} attempts: {last_error}")
