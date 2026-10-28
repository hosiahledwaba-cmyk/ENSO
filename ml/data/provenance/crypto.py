"""Cryptographic hashing, canonicalization, and authenticated signatures for climate provenance."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SIGNING_KEY_ID = "enso-pipeline-hmac-v1"
DEFAULT_PIPELINE_SECRET = "enso-shield-pipeline-internal-secret-2026"  # noqa: S105


def get_pipeline_signing_key() -> str:
    """Retrieve secret key for signing controlled internal pipeline artefacts."""
    return os.getenv("ENSO_PIPELINE_SIGNING_KEY", DEFAULT_PIPELINE_SECRET)


def compute_sha256(filepath: Path | str) -> str:
    """Compute standard SHA-256 hex digest of a file using 64KB streaming chunks."""
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"Cannot compute hash; file does not exist: {path}")
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_bytes_sha256(data: bytes) -> str:
    """Compute standard SHA-256 hex digest of in-memory byte sequence."""
    return hashlib.sha256(data).hexdigest()


def build_canonical_manifest_payload(manifest_data: dict[str, Any]) -> str:
    """Serialize the essential assertion fields into a deterministic canonical string.

    This ensures that signature generation and verification are independent of JSON formatting,
    whitespace, or key ordering.
    """
    canonical_dict = {
        "dataset_id": str(manifest_data.get("dataset_id", "")),
        "source_identifier": str(manifest_data.get("source_identifier", "")),
        "dataset_version": str(manifest_data.get("dataset_version", "")),
        "source_version": str(manifest_data.get("source_version", "")),
        "content_digest": str(manifest_data.get("content_digest", "")),
        "ingestion_timestamp_utc": str(manifest_data.get("ingestion_timestamp_utc", "")),
        "validation_status": str(manifest_data.get("validation_status", "")),
        "record_count": int(manifest_data.get("record_count", 0)),
        "processing_history_length": len(manifest_data.get("processing_history", [])),
    }
    return json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))


def sign_provenance_manifest(
    manifest_data: dict[str, Any],
    secret_key: str | None = None,
    key_id: str = DEFAULT_SIGNING_KEY_ID,
) -> tuple[str, str]:
    """Generate an authenticated HMAC-SHA256 signature for controlled pipeline artefacts.

    Unsigned third-party external downloads must never be signed by this function.

    Returns:
        tuple of (hex_signature, key_id).
    """
    key = (secret_key or get_pipeline_signing_key()).encode("utf-8")
    canonical_payload = build_canonical_manifest_payload(manifest_data).encode("utf-8")
    signature = hmac.new(key, canonical_payload, hashlib.sha256).hexdigest()
    return signature, key_id


def verify_provenance_signature(
    manifest_data: dict[str, Any],
    signature: str | None,
    secret_key: str | None = None,
) -> bool:
    """Verify HMAC-SHA256 signature using constant-time comparison.

    Returns False if signature is missing, empty, or does not match canonical payload.
    """
    if not signature:
        return False
    key = (secret_key or get_pipeline_signing_key()).encode("utf-8")
    canonical_payload = build_canonical_manifest_payload(manifest_data).encode("utf-8")
    expected_sig = hmac.new(key, canonical_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


def determine_authenticity_status(
    is_controlled_pipeline: bool,
    signature: str | None,
    manifest_data: dict[str, Any],
    secret_key: str | None = None,
) -> str:
    """Clearly distinguish source authenticity from content integrity.

    CRITICAL RULE:
    Unsigned third-party data is NEVER marked as authenticated merely because a
    cryptographic digest was computed. A hash digest proves content integrity against post-ingestion
    tampering, but does NOT establish source authenticity unless accompanied by a verified
    cryptographic signature from a trusted authority or controlled pipeline.
    """
    if not is_controlled_pipeline:
        return "UNSIGNED_THIRD_PARTY"

    if verify_provenance_signature(manifest_data, signature, secret_key=secret_key):
        return "AUTHENTIC_CONTROLLED_PIPELINE"

    return "SIGNATURE_INVALID"
