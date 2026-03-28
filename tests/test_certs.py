import os
import stat
import tempfile
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from aetheredge.certs import generate_self_signed_cert, get_or_create_certs
from aetheredge.identity import _generate_keypair


NODE_ID = "aether-testnode00000000000000000000"


@pytest.fixture
def keypair():
    return _generate_keypair()


def test_generate_cert_creates_files(keypair):
    private_pem, _ = keypair
    with tempfile.TemporaryDirectory() as tmp:
        cert_path, key_path = generate_self_signed_cert(NODE_ID, private_pem, tmp)
        assert cert_path.exists()
        assert key_path.exists()


def test_cert_subject_cn(keypair):
    private_pem, _ = keypair
    with tempfile.TemporaryDirectory() as tmp:
        cert_path, _ = generate_self_signed_cert(NODE_ID, private_pem, tmp)
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        assert cn == NODE_ID


def test_cert_san(keypair):
    private_pem, _ = keypair
    with tempfile.TemporaryDirectory() as tmp:
        cert_path, _ = generate_self_signed_cert(NODE_ID, private_pem, tmp)
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        assert NODE_ID in dns_names


def test_cert_validity_10_years(keypair):
    private_pem, _ = keypair
    with tempfile.TemporaryDirectory() as tmp:
        cert_path, _ = generate_self_signed_cert(NODE_ID, private_pem, tmp)
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        delta = cert.not_valid_after_utc - cert.not_valid_before_utc
        assert delta.days >= 3649


def test_cert_file_permissions(keypair):
    private_pem, _ = keypair
    with tempfile.TemporaryDirectory() as tmp:
        cert_path, key_path = generate_self_signed_cert(NODE_ID, private_pem, tmp)
        assert stat.S_IMODE(os.stat(cert_path).st_mode) == 0o644
        assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600


def test_get_or_create_certs_idempotent(keypair):
    private_pem, _ = keypair
    with tempfile.TemporaryDirectory() as tmp:
        p1, k1 = get_or_create_certs(NODE_ID, private_pem, tmp)
        mtime_cert = os.path.getmtime(p1)
        mtime_key = os.path.getmtime(k1)
        p2, k2 = get_or_create_certs(NODE_ID, private_pem, tmp)
        assert p1 == p2
        assert k1 == k2
        # Files should not have been re-written
        assert os.path.getmtime(p2) == mtime_cert
        assert os.path.getmtime(k2) == mtime_key
