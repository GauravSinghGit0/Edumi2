"""
Generate a self-signed SSL/TLS certificate for edumi.ac.in

Usage:
    python scripts/generate_ssl_cert.py

Generates:
    certs/edumi.key   — RSA 2048-bit private key
    certs/edumi.crt   — Self-signed certificate (valid 10 years)

Subject Alternative Names (SANs) covered:
    - edumi.ac.in
    - www.edumi.ac.in
    - localhost / 127.0.0.1 / ::1
"""

from pathlib import Path
import socket
import datetime

# Try modern cryptography library first, fall back to pyOpenSSL
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    USE_CRYPTOGRAPHY = True
except ImportError:
    from OpenSSL import crypto
    USE_CRYPTOGRAPHY = False

# Paths
CERT_DIR = Path(__file__).resolve().parent.parent / "certs"
CERT_DIR.mkdir(parents=True, exist_ok=True)

KEY_FILE  = CERT_DIR / "edumi.key"
CERT_FILE = CERT_DIR / "edumi.crt"

DOMAIN = "eclass.dei.ac.in"


def generate_with_cryptography():
    import ipaddress
    # ── Root CA ───────────────────────────────────────────────────────
    ca_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    ca_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EduMi Academic Local CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "EduMi Local Root CA"),
    ])

    now = datetime.datetime.utcnow()
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365 * 10))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256(), default_backend())
    )

    # ── Server/Leaf Key ───────────────────────────────────────────────
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # ── Subject Alternative Names ─────────────────────────────────────
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"

    san_list = [
        x509.DNSName(DOMAIN),
        x509.DNSName(f"www.{DOMAIN}"),
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipaddress.IPv6Address("::1")),
    ]
    
    # Add local IP if it's different from 127.0.0.1
    if local_ip != "127.0.0.1":
        try:
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
        except Exception:
            pass

    # ── Server/Leaf Certificate ───────────────────────────────────────
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Maharashtra"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Pune"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EduMi Academic"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "IT Department"),
        x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365 * 10))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256(), default_backend())
    )

    # ── Write to disk ─────────────────────────────────────────────────
    CA_KEY_FILE = CERT_DIR / "edumi-root-ca.key"
    CA_CERT_FILE = CERT_DIR / "edumi-root-ca.crt"
    TRUST_FILE = CERT_DIR / "edumi-trust-this.crt"

    CA_KEY_FILE.write_bytes(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
    )
    CA_CERT_FILE.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    TRUST_FILE.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    KEY_FILE.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
    )
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"[OK] Root CA Key    -> {CA_KEY_FILE}")
    print(f"[OK] Root CA Cert   -> {CA_CERT_FILE}")
    print(f"[OK] Server Key     -> {KEY_FILE}")
    print(f"[OK] Server Cert    -> {CERT_FILE}")
    print(f"[OK] Trust Cert     -> {TRUST_FILE}")
    print(f"     Domain         : {DOMAIN}")
    print(f"     Valid until    : {now.year + 10}-xx-xx")
    print(f"     SANs           : {len(san_list)} entries")
    print()
    print("NOTE: Root CA generated and trusted certificate copied to edumi-trust-this.crt.")


def generate_with_pyopenssl():
    """Generate using legacy pyOpenSSL library"""
    # ── Root CA ───────────────────────────────────────────────────────
    ca_key = crypto.PKey()
    ca_key.generate_key(crypto.TYPE_RSA, 2048)

    ca_cert = crypto.X509()
    ca_subj = ca_cert.get_subject()
    ca_subj.C  = "IN"
    ca_subj.O  = "EduMi Academic Local CA"
    ca_subj.CN = "EduMi Local Root CA"
    ca_cert.set_serial_number(1)
    ca_cert.set_issuer(ca_subj)
    ca_cert.gmtime_adj_notBefore(-86400)
    ca_cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    ca_cert.set_pubkey(ca_key)
    ca_cert.add_extensions([
        crypto.X509Extension(b"basicConstraints", True, b"CA:TRUE"),
        crypto.X509Extension(b"keyUsage", True, b"keyCertSign, cRLSign"),
    ])
    ca_cert.sign(ca_key, "sha256")

    # ── Server/Leaf Key ───────────────────────────────────────────────
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)

    # ── Server/Leaf Certificate ───────────────────────────────────────
    cert = crypto.X509()

    subject = cert.get_subject()
    subject.C  = "IN"
    subject.ST = "Maharashtra"
    subject.L  = "Pune"
    subject.O  = "EduMi Academic"
    subject.OU = "IT Department"
    subject.CN = DOMAIN

    cert.set_serial_number(1000)
    cert.set_issuer(ca_subj) # issuer is CA subject

    cert.gmtime_adj_notBefore(-86400)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_pubkey(key)

    # ── Extensions (Subject Alternative Names) ────────────────────────
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"

    san_entries = [
        f"DNS:{DOMAIN}",
        f"DNS:www.{DOMAIN}",
        f"DNS:localhost",
        "IP:127.0.0.1",
        "IP:::1",
        f"IP:{local_ip}",
    ]
    san_entries = list(dict.fromkeys(san_entries))

    cert.add_extensions([
        crypto.X509Extension(
            b"subjectAltName", False, ", ".join(san_entries).encode()
        ),
        crypto.X509Extension(
            b"basicConstraints", True, b"CA:FALSE"
        ),
        crypto.X509Extension(
            b"keyUsage", True, b"digitalSignature, keyEncipherment"
        ),
        crypto.X509Extension(
            b"extendedKeyUsage", False, b"serverAuth, clientAuth"
        ),
    ])

    # ── Sign ──────────────────────────────────────────────────────────
    cert.sign(ca_key, "sha256")

    # ── Write to disk ─────────────────────────────────────────────────
    CA_KEY_FILE = CERT_DIR / "edumi-root-ca.key"
    CA_CERT_FILE = CERT_DIR / "edumi-root-ca.crt"
    TRUST_FILE = CERT_DIR / "edumi-trust-this.crt"

    CA_KEY_FILE.write_bytes(crypto.dump_privatekey(crypto.FILETYPE_PEM, ca_key))
    CA_CERT_FILE.write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))
    TRUST_FILE.write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))

    KEY_FILE.write_bytes(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
    CERT_FILE.write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

    print(f"[OK] Root CA Key    -> {CA_KEY_FILE}")
    print(f"[OK] Root CA Cert   -> {CA_CERT_FILE}")
    print(f"[OK] Server Key     -> {KEY_FILE}")
    print(f"[OK] Server Cert    -> {CERT_FILE}")
    print(f"[OK] Trust Cert     -> {TRUST_FILE}")
    print(f"     Domain         : {DOMAIN}")
    print(f"     Valid until    : {now.year + 10}-xx-xx")
    print(f"     SANs           : {', '.join(san_entries)}")


if __name__ == "__main__":
    if USE_CRYPTOGRAPHY:
        import ipaddress
        print("Using cryptography library...")
        generate_with_cryptography()
    else:
        print("Using pyOpenSSL library...")
        generate_with_pyopenssl()
