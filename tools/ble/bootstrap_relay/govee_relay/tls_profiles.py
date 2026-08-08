from __future__ import annotations

import os
import shutil
import ssl
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .guards import assert_context_has_no_keylog

DEVICE_CIPHER = "AES256-SHA256"


@dataclass(frozen=True, slots=True)
class CertificateFiles:
    certificate: Path
    private_key: Path


def _run_openssl(*arguments: str) -> str:
    executable = shutil.which("openssl")
    if executable is None:
        raise RuntimeError("openssl is required")
    result = subprocess.run(  # noqa: S603 - arguments are fixed by this private tool
        (executable, *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def generate_test_certificate(
    directory: Path,
    hostname: str,
    *,
    algorithm: str = "rsa",
) -> CertificateFiles:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    certificate = directory / "certificate.pem"
    private_key = directory / "private-key.pem"
    if algorithm == "rsa":
        key_arguments: tuple[str, ...] = ("-newkey", "rsa:2048")
    elif algorithm == "ecdsa":
        key_arguments = (
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
        )
    else:
        raise ValueError(f"unsupported certificate algorithm {algorithm!r}")
    _run_openssl(
        "req",
        "-x509",
        *key_arguments,
        "-nodes",
        "-days",
        "2",
        "-subj",
        f"/CN={hostname}",
        "-addext",
        f"subjectAltName=DNS:{hostname}",
        "-keyout",
        str(private_key),
        "-out",
        str(certificate),
    )
    os.chmod(directory, 0o700)
    os.chmod(certificate, 0o600)
    os.chmod(private_key, 0o600)
    return CertificateFiles(certificate, private_key)


def certificate_is_rsa(certificate: Path) -> bool:
    details = _run_openssl("x509", "-in", str(certificate), "-noout", "-text")
    return "Public Key Algorithm: rsaEncryption" in details


def build_device_server_context(files: CertificateFiles) -> ssl.SSLContext:
    if not certificate_is_rsa(files.certificate):
        raise ValueError("the H6199 device-facing certificate must use RSA")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(f"{DEVICE_CIPHER}:@SECLEVEL=1")
    context.load_cert_chain(files.certificate, files.private_key)
    context.keylog_filename = None  # type: ignore[assignment]
    assert_context_has_no_keylog(context)
    return context


def build_test_client_context(certificate: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(f"{DEVICE_CIPHER}:@SECLEVEL=1")
    context.load_verify_locations(cafile=certificate)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.keylog_filename = None  # type: ignore[assignment]
    assert_context_has_no_keylog(context)
    return context


def build_upstream_context(*, ca_file: Path | None = None) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=ca_file)
    context.keylog_filename = None  # type: ignore[assignment]
    assert_context_has_no_keylog(context)
    return context
