from __future__ import annotations

import os
import resource
import ssl
from collections.abc import Iterable


def harden_process() -> None:
    """Apply controls that must precede TLS or secret-bearing data."""
    os.umask(0o077)
    os.environ.pop("SSLKEYLOGFILE", None)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def assert_context_has_no_keylog(context: ssl.SSLContext) -> None:
    if context.keylog_filename is not None:
        raise RuntimeError("TLS key logging must remain disabled")


def assert_secrets_absent_from_environment(secrets: Iterable[str]) -> None:
    environment = "\0".join(f"{key}={value}" for key, value in os.environ.items())
    leaked = [secret for secret in secrets if secret and secret in environment]
    if leaked:
        raise RuntimeError("a fabricated secret reached the process environment")


def core_dumps_disabled() -> bool:
    return resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
