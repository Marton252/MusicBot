"""Generate a self-signed TLS certificate for the web dashboard."""

import datetime
import os
import stat
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_certificate(cert_dir: str = "certs") -> None:
    os.makedirs(cert_dir, exist_ok=True)
    key_path = os.path.join(cert_dir, "key.pem")
    cert_path = os.path.join(cert_dir, "cert.pem")

    # Generate a private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate a self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    # Finding #19: Use timezone-aware datetime (utcnow is deprecated since 3.12)
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("127.0.0.1"),
            ]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    # Write key — Finding #08: unencrypted but with restrictive permissions
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Set restrictive file permissions (owner-only read/write)
    if sys.platform != "win32":
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Successfully generated self-signed certificate in {cert_dir}/")
    print(f"  Certificate: {cert_path}")
    print(f"  Private key: {key_path}")


if __name__ == "__main__":
    generate_certificate()
