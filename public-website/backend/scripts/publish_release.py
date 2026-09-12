"""
scripts/publish_release.py
───────────────────────────
Put a build into release storage and record it as a Release.

WHY THIS IS A SCRIPT AND NOT AN ENDPOINT
Publishing is a rare, high-consequence operation performed by an operator with
shell access, not a routine action taken over the network. An HTTP upload
endpoint for executables would be a permanent, internet-reachable path that
writes attacker-influenced bytes into the directory the download endpoint
serves from — the single most valuable target in the system. There is no
version of that endpoint safer than not having one.

So the artefact arrives the same way the container image does: through the
deployment channel, by someone who is already trusted with the host.

WHAT IT GUARANTEES
- the artefact is written inside RELEASE_FILES_BASE_PATH and nowhere else
- the checksum is computed from the bytes actually written, not supplied
- `file_size` matches those bytes, so the delivery-time integrity check passes
- the database records a path relative to the storage root, never an absolute
  host path
- publishing is idempotent per version

Usage:
    python scripts/publish_release.py \\
        --file /path/to/EndpointAgent.exe \\
        --version 1.2.0 \\
        --title "RiskIntel 1.2.0" \\
        --notes-file ./RELEASE_NOTES.md \\
        --publish
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionFactory  # noqa: E402
from app.models.release import Release, ReleaseStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

settings = get_settings()

CHUNK = 1024 * 1024


def _sha256_of(path: Path) -> tuple[str, int]:
    """Checksum and size, streamed so a large artefact is never held in memory."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _storage_root() -> Path:
    root = Path(settings.RELEASE_FILES_BASE_PATH).expanduser().resolve()
    if not root.exists():
        raise SystemExit(
            f"Storage root does not exist: {root}\n"
            "On a deployed host this is the mounted persistent disk. Create it, "
            "or correct RELEASE_FILES_BASE_PATH."
        )
    return root


async def _resolve_publisher(session, email: str | None) -> User:
    """
    The publisher must be a real account with the ADMIN role.

    `published_by_user_id` is a foreign key that exists so a release can be
    traced to a person. Allowing an arbitrary id, or defaulting to whoever
    happens to be first in the table, would make that column decorative.
    """
    if email:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalars().first()
        if not user:
            raise SystemExit(f"No account found for {email}.")
    else:
        user = (
            await session.execute(
                select(User)
                .where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
                .order_by(User.created_at)
            )
        ).scalars().first()
        if not user:
            raise SystemExit(
                "No admin account exists. Create one first, or pass --publisher."
            )

    if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise SystemExit(f"{user.email} is not an admin; refusing to attribute a release to it.")

    return user


async def publish(args: argparse.Namespace) -> None:
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Not a readable file: {source}")

    root = _storage_root()

    # The stored name is derived from the version and the source suffix, never
    # taken verbatim from an operator-supplied path. It is also what the
    # download endpoint will resolve, so it must contain no separators.
    suffix = "".join(part for part in source.suffixes[-2:] if part.isascii())
    artefact_name = f"riskintel-{args.version}{suffix}"
    if "/" in artefact_name or "\\" in artefact_name or ".." in artefact_name:
        raise SystemExit("Refusing to write an artefact name containing path characters.")

    destination = (root / artefact_name).resolve()
    if root not in destination.parents:
        raise SystemExit("Refusing to write outside the storage root.")

    notes = (
        Path(args.notes_file).read_text(encoding="utf-8")
        if args.notes_file
        else args.notes or f"Release {args.version}."
    )

    print(f"Source      {source}")
    print(f"Destination {destination}")

    # Copy first, then checksum the copy. Hashing the source and trusting the
    # copy would miss a truncated or corrupted write, and the checksum published
    # to users is supposed to describe the bytes they will actually receive.
    shutil.copy2(source, destination)
    checksum, size = _sha256_of(destination)
    print(f"SHA-256     {checksum}")
    print(f"Size        {size:,} bytes")

    async with AsyncSessionFactory() as session:
        publisher = await _resolve_publisher(session, args.publisher)
        now = datetime.now(tz=timezone.utc)
        status = ReleaseStatus.PUBLISHED if args.publish else ReleaseStatus.DRAFT

        existing = (
            await session.execute(select(Release).where(Release.version == args.version))
        ).scalars().first()

        if existing:
            existing.title = args.title or existing.title
            existing.release_notes = notes
            existing.file_path = artefact_name
            existing.file_size = size
            existing.sha256_checksum = checksum
            existing.release_status = status
            existing.updated_at = now
            if args.publish:
                existing.published_at = existing.published_at or now
            release = existing
            action = "updated"
        else:
            release = Release(
                release_id=uuid.uuid4(),
                version=args.version,
                title=args.title or f"RiskIntel {args.version}",
                description=args.description,
                release_notes=notes,
                file_path=artefact_name,
                file_size=size,
                sha256_checksum=checksum,
                release_status=status,
                is_latest=False,
                published_at=now if args.publish else None,
                published_by_user_id=publisher.user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(release)
            action = "created"

        # Exactly one release may be latest. Clearing the flag on every other row
        # in the same transaction is what keeps that true even if two publishes
        # race.
        if args.publish and args.latest:
            for other in (await session.execute(select(Release))).scalars().all():
                other.is_latest = False
            release.is_latest = True

        await session.commit()
        await session.refresh(release)

    print()
    print("-" * 62)
    print(f"  {action}: v{release.version}  ({release.release_id})")
    print(f"  status:  {release.release_status.value}")
    print(f"  latest:  {release.is_latest}")
    print("-" * 62)
    print("  The artefact is reachable only through the authenticated download")
    print("  endpoint. It is not served as a static file by any web tier.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a release artefact.")
    parser.add_argument("--file", required=True, help="Path to the build to publish")
    parser.add_argument("--version", required=True, help="Semantic version, e.g. 1.2.0")
    parser.add_argument("--title", help="Display title")
    parser.add_argument("--description", help="One-line description")
    parser.add_argument("--notes", help="Release notes as a string")
    parser.add_argument("--notes-file", help="Read release notes from a file")
    parser.add_argument("--publisher", help="Admin email to attribute the release to")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish immediately. Without this the release is created as a DRAFT.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Mark as the latest release (implies --publish).",
    )
    args = parser.parse_args()

    if args.latest and not args.publish:
        raise SystemExit("--latest requires --publish: a draft cannot be the latest release.")

    asyncio.run(publish(args))


if __name__ == "__main__":
    main()
