"""Object storage abstraction (app/services/storage.py).

`LocalFilesystemStorage` is already exercised indirectly by every test
in test_evidence.py (it's the default backend). `S3Storage` has no real
AWS/MinIO instance available to test against in this environment, so
it is tested here against `moto`'s mocked S3 -- a real boto3 client
talking to an in-process fake that implements the actual S3 HTTP API
(not a hand-rolled stub), which is the standard way to integration-test
S3 client code without a live AWS account. This is NOT the same as
testing against a real S3-compatible service (see IMPLEMENTATION-NOTES.md
for the honest distinction) -- it verifies the S3Storage class speaks
correct S3 API calls and round-trips bytes correctly, not real-network
behavior, IAM policy enforcement, or bucket-policy access boundaries.
"""
from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from app.services.storage import LocalFilesystemStorage, S3Storage


@pytest.fixture
def s3_storage():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-quarantine")
        client.create_bucket(Bucket="test-evidence")
        yield S3Storage(
            quarantine_bucket="test-quarantine",
            evidence_bucket="test-evidence",
            region_name="us-east-1",
            endpoint_url=None,
            access_key_id=None,
            secret_access_key=None,
        )


async def test_s3_write_then_read_quarantine_round_trips(s3_storage):
    await s3_storage.write_quarantine("poc-1/artifact-1_evidence.pdf", b"%PDF-1.4 fake pdf bytes")
    data = await s3_storage.read_quarantine("poc-1/artifact-1_evidence.pdf")
    assert data == b"%PDF-1.4 fake pdf bytes"


async def test_s3_read_quarantine_missing_key_returns_none(s3_storage):
    assert await s3_storage.read_quarantine("never-written") is None


async def test_s3_promote_to_evidence_moves_bucket_and_clears_quarantine(s3_storage):
    key = "poc-1/artifact-2_clean.pdf"
    await s3_storage.write_quarantine(key, b"clean content")
    await s3_storage.promote_to_evidence(key, b"clean content")

    assert await s3_storage.read_quarantine(key) is None  # removed from quarantine

    import boto3 as _boto3

    client = _boto3.client("s3", region_name="us-east-1")
    obj = client.get_object(Bucket="test-evidence", Key=key)
    assert obj["Body"].read() == b"clean content"


async def test_s3_delete_quarantine_removes_infected_artifact(s3_storage):
    key = "poc-1/artifact-3_infected.pdf"
    await s3_storage.write_quarantine(key, b"EICAR-FAKE-TEST-MARKER")
    await s3_storage.delete_quarantine(key)
    assert await s3_storage.read_quarantine(key) is None


async def test_local_and_s3_backends_satisfy_the_same_contract(tmp_path, s3_storage):
    """Both backends implement the exact same quarantine -> promote /
    quarantine -> delete behavior -- the protocol
    app/services/evidence_service.py actually depends on.
    """
    local_storage = LocalFilesystemStorage(
        quarantine_dir=str(tmp_path / "quarantine"), evidence_dir=str(tmp_path / "evidence")
    )

    for storage in (local_storage, s3_storage):
        key = f"contract-check/{type(storage).__name__}.txt"
        await storage.write_quarantine(key, b"contract bytes")
        assert await storage.read_quarantine(key) == b"contract bytes"
        await storage.promote_to_evidence(key, b"contract bytes")
        assert await storage.read_quarantine(key) is None
