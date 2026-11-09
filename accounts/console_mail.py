"""Print emails in the terminal as plain text when running the site locally.

Django's console backend prints the raw email. Long lines such as the
verify-email and reset-password links come out quoted-printable: an "=" is put
in the middle of the link and the rest goes on the next line, so a copied link
is cut short and the site says it has expired. This backend prints the headers
people need and the body exactly as written, so the links work when copied.
"""

from django.core.mail.backends.console import EmailBackend as ConsoleBackend

HEADERS = ("From", "To", "Cc", "Subject")


class EmailBackend(ConsoleBackend):
    def write_message(self, message):
        msg = message.message()
        for name in HEADERS:
            if msg[name]:
                self.stream.write(f"{name}: {msg[name]}\n")
        self.stream.write(f"\n{message.body}\n")
        self.stream.write("-" * 79)
        self.stream.write("\n")
