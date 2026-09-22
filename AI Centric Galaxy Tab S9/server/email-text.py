"""Read a user-selected .eml without loading remote content or executing HTML."""
import base64
import json
import sys
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.hidden += 1
        if tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.hidden:
            self.hidden -= 1

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


with open(sys.argv[1], "rb") as source:
    message = BytesParser(policy=policy.default).parsebytes(source.read(8_000_001))
headers = "\n".join(f"{key}: {str(message.get(key, ''))[:4000]}" for key in ("Subject", "From", "To", "Cc", "Date", "Message-ID"))
body = message.get_body(preferencelist=("plain", "html"))
text = ""
if body is not None:
    text = body.get_content()
    if not isinstance(text, str):
        text = text.decode("utf-8", errors="replace")
    if body.get_content_type() == "text/html":
        parser = TextOnly()
        parser.feed(text)
        text = "".join(parser.parts)
attachments = []
for part in message.walk():
    if part.get_filename():
        data = part.get_payload(decode=True)
        if data is not None:
            attachments.append({"name": str(part.get_filename())[:240], "data": base64.b64encode(data).decode("ascii")})
        if len(attachments) > 50:
            raise ValueError("Too many email attachments")
print(json.dumps({"text": headers + "\n\n" + text[:200_000], "truncated": len(text) > 200_000, "attachments": attachments}))
