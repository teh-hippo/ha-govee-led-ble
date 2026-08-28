"""Development-only editor module URL contract."""

from __future__ import annotations

import ipaddress
import os
import sys
from collections.abc import Mapping
from urllib.parse import SplitResult, urlsplit

EDITOR_DEV_MODULE_URL_ENV = "HA_GOVEE_LED_BLE_EDITOR_DEV_MODULE_URL"
_MODULE_SUFFIXES = (".js", ".ts")


def validate_editor_dev_module_url(value: str) -> SplitResult:
    """Validate a local development module URL."""
    if not value or value != value.strip():
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must be a non-empty URL without surrounding whitespace")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as err:
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must be a valid URL") from err
    if parsed.scheme != "http":
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must use http")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must not contain a query or fragment")
    if port is None:
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must include an explicit port")
    if hostname is None:
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} must include a host")
    if hostname != "localhost":
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as err:
            raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} host must be localhost or a local IP address") from err
        if (
            address.is_unspecified
            or address.is_multicast
            or not (address.is_loopback or address.is_private or address.is_link_local)
        ):
            raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} host must be localhost or a local IP address")
    if not parsed.path.startswith("/") or not parsed.path.endswith(_MODULE_SUFFIXES):
        raise ValueError(f"{EDITOR_DEV_MODULE_URL_ENV} path must name a JavaScript or TypeScript module")
    return parsed


def editor_dev_module_url(environ: Mapping[str, str] = os.environ) -> str | None:
    """Return the explicit development module URL when configured."""
    value = environ.get(EDITOR_DEV_MODULE_URL_ENV)
    if value is None:
        return None
    validate_editor_dev_module_url(value)
    return value


def _main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} URL", file=sys.stderr)
        return 2
    try:
        parsed = validate_editor_dev_module_url(sys.argv[1])
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    print(f"{parsed.hostname}\t{parsed.port}\t{parsed.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
