"""AES-GCM (``0xE711``) encryption support for newer Govee BLE devices.

Self-contained: nothing outside this package knows the scheme exists beyond a
handful of call sites in :mod:`..coordinator`. Devices that do not offer the
``2b12`` marker keep the plaintext path untouched.
"""

from .crypto import GoveeCryptoError
from .session import GoveeEncryptionSession

__all__ = ["GoveeCryptoError", "GoveeEncryptionSession"]
