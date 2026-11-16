"""Object storage abstraction for evidence artifacts -- quarantine and
serving buckets kept structurally separate, per
architecture/TASD-v1.0.md section 9.5/15.4.

Two implementations behind the same `ObjectStorage` protocol, exactly
the pattern `app/services/ai/client.py` already uses for AI providers:
`LocalFilesystemStorage` (two local directories, this build's dev/test
default and the one every existing evidence test already runs
against) and `S3Storage` (real S3-compatible object storage, selected
by `STORAGE_BACKEND=s3`). `app/services/evidence_service.py` depends on
this protocol only -- it never branches on which backend is active, and
nothing about the magic-byte validation, the quarantine-then-scan flow,
or the "only a human transition can reach Verified/Rejected" rule
changes based on storage backend.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ObjectStorage(Protocol):
    async def write_quarantine(self, key: str, data: bytes) -> None: ...

    async def read_quarantine(self, key: str) -> bytes | None:
        """Returns None if the key does not exist in quarantine (already
        scanned and moved/deleted, or never written)."""
        ...

    async def delete_quarantine(self, key: str) -> None: ...

    async def promote_to_evidence(self, key: str, data: bytes) -> None:
        """Writes `data` to the evidence (serving) location and removes
        it from quarantine -- the Clean-scan outcome. Takes `data`
        explicitly (rather than re-reading quarantine) so the caller's
        already-in-memory bytes are reused instead of round-tripping
        through storage twice.
        """
        ...


class LocalFilesystemStorage:
    """Local-filesystem stand-in used for local development and the
    automated test suite -- two directories under the configured
    `quarantine_dir`/`evidence_dir`, exactly the behavior this codebase
    had before the storage abstraction existed. Never used in a real
    production deployment (TASD-v1.0.md section 9.5 specifies real
    object storage); selected whenever `STORAGE_BACKEND` is not `s3`.
    """

    def __init__(self, quarantine_dir: str, evidence_dir: str):
        self._quarantine_dir = Path(quarantine_dir)
        self._evidence_dir = Path(evidence_dir)

    def _quarantine_path(self, key: str) -> Path:
        return self._quarantine_dir / key.replace("/", "__")

    def _evidence_path(self, key: str) -> Path:
        return self._evidence_dir / key.replace("/", "__")

    async def write_quarantine(self, key: str, data: bytes) -> None:
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._quarantine_path(key).write_bytes(data)

    async def read_quarantine(self, key: str) -> bytes | None:
        path = self._quarantine_path(key)
        return path.read_bytes() if path.exists() else None

    async def delete_quarantine(self, key: str) -> None:
        path = self._quarantine_path(key)
        if path.exists():
            path.unlink()

    async def promote_to_evidence(self, key: str, data: bytes) -> None:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        self._evidence_path(key).write_bytes(data)
        quarantine_path = self._quarantine_path(key)
        if quarantine_path.exists():
            quarantine_path.unlink()


class S3Storage:
    """Real S3-compatible object storage, via `boto3` (an optional
    import, kept out of the module-level namespace exactly like
    `anthropic`/`google.genai` in app/services/ai/client.py, so
    environments without `boto3` installed and `STORAGE_BACKEND=local`
    are unaffected).

    Quarantine and evidence are separate buckets (never separate
    prefixes in one bucket) so a bucket-level access policy can enforce
    "nothing in the quarantine bucket is ever world/app-readable" as an
    infrastructure-level guarantee, independent of this code -- the
    same quarantine/serving separation TASD-v1.0.md section 9.5/15.4
    specifies, now backed by a real access boundary rather than only a
    directory convention.
    """

    def __init__(
        self,
        *,
        quarantine_bucket: str,
        evidence_bucket: str,
        region_name: str | None,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ):
        import boto3  # local import: keeps boto3 optional, see docstring

        self._quarantine_bucket = quarantine_bucket
        self._evidence_bucket = evidence_bucket
        self._client = boto3.client(
            "s3",
            region_name=region_name,
            endpoint_url=endpoint_url,  # non-AWS S3-compatible services (e.g. MinIO)
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    async def write_quarantine(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._quarantine_bucket, Key=key, Body=data)

    async def read_quarantine(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            response = self._client.get_object(Bucket=self._quarantine_bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise

    async def delete_quarantine(self, key: str) -> None:
        self._client.delete_object(Bucket=self._quarantine_bucket, Key=key)

    async def promote_to_evidence(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._evidence_bucket, Key=key, Body=data)
        await self.delete_quarantine(key)


class StorageNotConfiguredError(RuntimeError):
    """Raised instead of constructing an `S3Storage` with blank bucket
    names (which would fail opaquely at the first real API call) --
    the same "explicit unconfigured state, never an invented default"
    rule `app/services/ai/client.py:ModelNotConfiguredError` applies to
    the AI provider credential.
    """


def get_storage() -> ObjectStorage:
    """Instantiates the backend selected by `STORAGE_BACKEND`
    (app/config.py) -- `app/services/evidence_service.py`'s one point
    of dependency on this module, mirroring
    `app/services/ai/factory.py:get_model_client`.
    """
    from app.config import get_settings

    settings = get_settings()
    if settings.storage_backend == "s3":
        if not settings.storage_configured:
            raise StorageNotConfiguredError(
                "STORAGE_BACKEND is 's3' but S3_QUARANTINE_BUCKET/S3_EVIDENCE_BUCKET are not both set."
            )
        return S3Storage(
            quarantine_bucket=settings.s3_quarantine_bucket,
            evidence_bucket=settings.s3_evidence_bucket,
            region_name=settings.s3_region or None,
            endpoint_url=settings.s3_endpoint_url or None,
            access_key_id=settings.aws_access_key_id.get_secret_value() or None,
            secret_access_key=settings.aws_secret_access_key.get_secret_value() or None,
        )
    return LocalFilesystemStorage(quarantine_dir=settings.quarantine_dir, evidence_dir=settings.evidence_dir)
