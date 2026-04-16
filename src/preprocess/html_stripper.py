import email
import re
from html.parser import HTMLParser


class SmartHTMLExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False
        self.skip_tags = {"style", "script", "head"}

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip = True
        if tag in ("br", "p", "div", "tr", "td", "th", "li", "h1", "h2", "h3", "h4"):
            self.result.append("\n")

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.result.append(data)

    def get_text(self) -> str:
        text = "".join(self.result)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
        lines = [l for l in lines if l]
        return "\n".join(lines)


def strip_html(html: str) -> str:
    extractor = SmartHTMLExtractor()
    extractor.feed(html)
    return extractor.get_text()


def get_email_body(raw_email: bytes, max_chars: int = 8000) -> tuple[str, str]:
    msg = email.message_from_bytes(raw_email)

    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not text_body:
                try:
                    text_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
            elif ct == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        ct = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            return "", "none"

        if ct == "text/plain":
            text_body = payload
        elif ct == "text/html":
            html_body = payload

    if text_body and len(text_body) > 50:
        return text_body[:max_chars], "plain"
    elif html_body:
        stripped = strip_html(html_body)
        return stripped[:max_chars], "html_stripped"

    return "", "none"
