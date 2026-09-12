"""
scripts/manage_account.py
──────────────────────────
Create or adjust a single account from the host.

WHY THIS EXISTS, AND WHY IT IS SAFE IN PRODUCTION
Two operations cannot be performed over the API by design, and both are needed
on a real deployment:

  1. The FIRST admin. Roles are only grantable by an admin, so a fresh database
     has no way to produce one. Every system with role-based access has this
     bootstrap problem; the usual answer is an operator with shell access, which
     is what this is.

  2. Marking an address verified when mail is not deliverable. Verification is
     normally completed by following an emailed link. If SMTP is not configured
     or the provider is rejecting mail, an operator needs a way to unblock an
     account without weakening the verification endpoint for everyone.

Unlike `seed_dev.py` this is NOT blocked in production, because unlike seeding
it does not invent data — it acts on one named account, one attribute at a time,
at the explicit instruction of someone who already has shell access to the host.

Passwords are read interactively by default so they do not appear in shell
history or in `ps` output. `--password` exists for automation and warns.

Usage:
    python scripts/manage_account.py --email admin@example.com --create --role ADMIN --verified
    python scripts/manage_account.py --email someone@example.com --verified
    python scripts/manage_account.py --email someone@example.com --role USER
    python scripts/manage_account.py --email someone@example.com --deactivate
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password, validate_password_strength  # noqa: E402
from app.db.session import AsyncSessionFactory  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


def _read_password() -> str:
    """Prompt twice, off the terminal echo, and enforce the same policy as the API."""
    while True:
        first = getpass.getpass("New password: ")
        if first != getpass.getpass("Confirm password: "):
            print("  Passwords did not match. Try again.")
            continue
        violations = validate_password_strength(first)
        if violations:
            for violation in violations:
                print(f"  {violation}")
            continue
        return first


async def run(args: argparse.Namespace) -> None:
    async with AsyncSessionFactory() as session:
        user = (
            await session.execute(select(User).where(User.email == args.email))
        ).scalars().first()

        now = datetime.now(tz=timezone.utc)

        if user is None:
            if not args.create:
                raise SystemExit(
                    f"No account for {args.email}. Pass --create to make one."
                )

            password = args.password or _read_password()
            if args.password:
                print(
                    "  warning: --password was passed on the command line, where it is "
                    "visible in shell history and to `ps`. Prefer the prompt."
                )
            violations = validate_password_strength(password)
            if violations:
                raise SystemExit("Password rejected: " + "; ".join(violations))

            user = User(
                user_id=uuid.uuid4(),
                first_name=args.first_name or "Account",
                last_name=args.last_name or "Holder",
                email=args.email,
                password_hash=hash_password(password),
                country_code=args.country or "GB",
                company_name=args.company,
                role=UserRole[args.role] if args.role else UserRole.USER,
                email_verified=bool(args.verified),
                email_verified_at=now if args.verified else None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            action = "created"
        else:
            action = "updated"
            if args.password:
                violations = validate_password_strength(args.password)
                if violations:
                    raise SystemExit("Password rejected: " + "; ".join(violations))
                user.password_hash = hash_password(args.password)
            elif args.set_password:
                user.password_hash = hash_password(_read_password())

            if args.role:
                user.role = UserRole[args.role]
            if args.verified:
                user.email_verified = True
                user.email_verified_at = user.email_verified_at or now
            if args.unverify:
                user.email_verified = False
                user.email_verified_at = None
            if args.deactivate:
                user.is_active = False
            if args.activate:
                user.is_active = True

            user.updated_at = now

        await session.commit()
        await session.refresh(user)

    # Nothing secret is printed. Not the hash, not the password, not a token.
    print("-" * 58)
    print(f"  {action}: {user.email}")
    print(f"  role:     {user.role.value}")
    print(f"  verified: {user.email_verified}")
    print(f"  active:   {user.is_active}")
    print("-" * 58)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or adjust one account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--create", action="store_true", help="Create if absent")
    parser.add_argument("--role", choices=[r.name for r in UserRole])
    parser.add_argument("--verified", action="store_true", help="Mark email verified")
    parser.add_argument("--unverify", action="store_true", help="Clear verification")
    parser.add_argument("--deactivate", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--set-password", action="store_true", help="Prompt for a new password")
    parser.add_argument(
        "--password",
        help="Password for automation. Visible in shell history — prefer the prompt.",
    )
    parser.add_argument("--first-name")
    parser.add_argument("--last-name")
    parser.add_argument("--company")
    parser.add_argument("--country")
    args = parser.parse_args()

    if args.verified and args.unverify:
        raise SystemExit("--verified and --unverify contradict each other.")
    if args.activate and args.deactivate:
        raise SystemExit("--activate and --deactivate contradict each other.")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
