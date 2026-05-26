"""
Custom SMTP email backend that uses certifi's CA bundle.

On macOS (and some Linux distros), the system Python doesn't include root CAs,
which causes SSL certificate verification errors when connecting to SMTP servers.
This backend replaces the default SSL context with one that uses certifi's bundle.

Configure via settings.py:
    EMAIL_BACKEND = "guidewisey.email_backend.CertifiSMTPEmailBackend"
"""

import ssl

import certifi
from django.core.mail.backends.smtp import EmailBackend


class CertifiSMTPEmailBackend(EmailBackend):
    """SMTP backend that trusts certifi's CA bundle for TLS verification."""

    def open(self):
        if self.connection:
            return False

        import smtplib

        connection_params = {"local_hostname": None}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = ssl.create_default_context(cafile=certifi.where())

        try:
            self.connection = self.connection_class(self.host, self.port, **connection_params)

            if self.use_tls:
                ctx = ssl.create_default_context(cafile=certifi.where())
                self.connection.ehlo()
                self.connection.starttls(context=ctx)
                self.connection.ehlo()

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except smtplib.SMTPException:
            if not self.fail_silently:
                raise
