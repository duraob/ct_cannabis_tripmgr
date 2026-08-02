"""
Encryption for secrets held in the database.

Only the Azure client secret uses this today. The key lives in ENCRYPTION_KEY in the
environment, so an exposed database dump, backup or replica does not expose the secret.
It does not protect against someone who can already read files on the app server - the
key has to sit next to the app for unattended sending to work.

Generate a key once and keep it: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger('utils.crypto')


def _cipher():
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        raise Exception(
            "ENCRYPTION_KEY is not set - add it to .env before saving credentials. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value):
    """Encrypt a string for storage. Empty values are stored as-is."""
    if not value:
        return value
    return _cipher().encrypt(value.encode()).decode()


def decrypt(value):
    """Decrypt a stored string.

    Raises if the value cannot be decrypted, which means ENCRYPTION_KEY has changed
    since it was saved - the credential has to be re-entered.
    """
    if not value:
        return value
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise Exception(
            "Stored credential could not be decrypted - ENCRYPTION_KEY does not match "
            "the one used to save it. Re-enter the credential on the config page."
        )
