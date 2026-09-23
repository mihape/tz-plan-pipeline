"""Cryptographic hash calculation and integrity verification utilities."""

import hashlib
from pathlib import Path

CHUNK_SIZE = 65536  # 64 KB chunks for streaming


def compute_file_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hex digest of a file in streaming chunks.

    Args:
        file_path: Path to the target file.

    Returns:
        64-character lowercase hex string.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_bytes_sha256(content: bytes) -> str:
    """Compute the SHA-256 hex digest of in-memory bytes."""
    return hashlib.sha256(content).hexdigest()


def verify_file_sha256(file_path: Path, expected_hash: str) -> bool:
    """Verify that a file's SHA-256 matches the expected digest."""
    return compute_file_sha256(file_path).lower() == expected_hash.strip().lower()
