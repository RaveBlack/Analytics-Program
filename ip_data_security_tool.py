"""
IP & Data Security Tool (CLI, privacy-first)

Core features:
- IP validation (IPv4/IPv6) + public/global check using ipaddress
- ASN / Organization metadata lookup (NO geolocation)
- Password hashing locally (SHA-256; optional bcrypt if installed)
- Email validation + masking

Privacy constraints:
- No location/city/country/coords lookups.
- Password hashing is local-only (never sent to any API).
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys
from getpass import getpass
from typing import Any, Dict, NamedTuple, Optional, Tuple


EMAIL_RE = re.compile(
    # Practical validation (not fully RFC5322, but good UX).
    r"^(?P<local>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)"
    r"@"
    r"(?P<domain>[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)$"
)


class UserInputError(ValueError):
    pass


class IpCheckResult(NamedTuple):
    ip: str
    version: int
    is_public: bool
    reason: str


def _try_import_requests():
    try:
        import requests  # type: ignore
    except Exception:
        return None
    return requests


def parse_ip(ip_str: str) -> ipaddress._BaseAddress:
    ip_str = (ip_str or "").strip()
    if not ip_str:
        raise UserInputError("Empty IP address.")
    try:
        return ipaddress.ip_address(ip_str)
    except ValueError:
        raise UserInputError("Invalid IP address. Enter a valid IPv4 or IPv6 address.") from None


def check_public_ip(ip_obj: ipaddress._BaseAddress) -> IpCheckResult:
    # ipaddress considers "public internet-connected" addresses as is_global.
    # This excludes private, loopback, link-local, multicast, reserved, etc.
    is_public = bool(getattr(ip_obj, "is_global", False))
    if is_public:
        reason = "Public (globally routable)"
    else:
        # Provide a helpful explanation without leaking into geolocation.
        flags = []
        for name in (
            "is_private",
            "is_loopback",
            "is_link_local",
            "is_multicast",
            "is_reserved",
            "is_unspecified",
        ):
            try:
                if getattr(ip_obj, name):
                    flags.append(name.replace("is_", "").replace("_", "-"))
            except Exception:
                pass
        reason = "Not public/global (" + (", ".join(flags) if flags else "non-global") + ")"

    return IpCheckResult(ip=str(ip_obj), version=ip_obj.version, is_public=is_public, reason=reason)


def fetch_asn_metadata(ip_str: str, *, timeout_s: float = 10.0) -> Dict[str, str]:
    """
    Fetch ASN/Org metadata for an IP address with NO geolocation.

    Uses BGPView's IP API (returns ASN/prefix info; no GPS/city/country requirement).
    """
    requests = _try_import_requests()
    if requests is None:
        raise RuntimeError("Missing dependency: requests. Install with: pip install requests")

    url = f"https://api.bgpview.io/ip/{ip_str}"
    resp = requests.get(url, timeout=timeout_s, headers={"Accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()

    # Expected: {"status":"ok","data":{...}}
    if not isinstance(data, dict) or data.get("status") != "ok":
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("status_message") or data.get("message") or "")
        raise RuntimeError(f"ASN lookup failed. {msg}".strip())

    d = data.get("data") or {}
    if not isinstance(d, dict):
        raise RuntimeError("ASN lookup failed: unexpected response shape.")

    # Pull a best-effort ASN record from prefixes list.
    prefixes = d.get("prefixes") or []
    asn_obj: Dict[str, Any] = {}
    if isinstance(prefixes, list) and prefixes:
        first = prefixes[0]
        if isinstance(first, dict):
            asn_obj = first.get("asn") or {}

    def s(v: Any) -> str:
        return "" if v is None else str(v)

    asn = s(asn_obj.get("asn"))
    as_name = s(asn_obj.get("name"))
    as_desc = s(asn_obj.get("description"))

    out: Dict[str, str] = {}
    if asn:
        out["ASN"] = asn
    if as_name:
        out["Organization"] = as_name
    if as_desc and as_desc != as_name:
        out["ISP/Org Description"] = as_desc
    return out


def sha256_hash(password: str) -> str:
    if password is None:
        password = ""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def bcrypt_hash(password: str, *, rounds: int = 12) -> str:
    try:
        import bcrypt  # type: ignore
    except Exception:
        raise RuntimeError("bcrypt is not installed. Install with: pip install bcrypt") from None

    pw = (password or "").encode("utf-8")
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(pw, salt).decode("utf-8")


def validate_email(email: str) -> Tuple[str, str]:
    email = (email or "").strip()
    m = EMAIL_RE.match(email)
    if not m:
        raise UserInputError("Invalid email format.")
    return m.group("local"), m.group("domain")


def mask_email(email: str) -> str:
    local, domain = validate_email(email)
    if len(local) == 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * (len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"


def _print_kv(title: str, kv: Dict[str, str]) -> None:
    print(title)
    if not kv:
        print("  (no data)")
        return
    for k in sorted(kv.keys()):
        print(f"  - {k}: {kv[k]}")


def cmd_ip(ip_str: str, *, lookup: bool, json_out: bool) -> int:
    try:
        ip_obj = parse_ip(ip_str)
        chk = check_public_ip(ip_obj)
        payload: Dict[str, Any] = {
            "ip": chk.ip,
            "ip_version": chk.version,
            "is_public": chk.is_public,
            "reason": chk.reason,
        }

        if lookup and chk.is_public:
            meta = fetch_asn_metadata(chk.ip)
            payload["asn_metadata"] = meta
        else:
            payload["asn_metadata"] = {}

        if json_out:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"IP: {chk.ip}")
            print(f"IP Version: IPv{chk.version}")
            print(f"Public: {'yes' if chk.is_public else 'no'} ({chk.reason})")
            if lookup and chk.is_public:
                _print_kv("ASN / Network Metadata:", payload["asn_metadata"])
            elif lookup and not chk.is_public:
                print("ASN / Network Metadata: (skipped; IP is not public/global)")
        return 0
    except UserInputError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Lookup error: {e}", file=sys.stderr)
        return 1


def cmd_hash(*, algo: str, json_out: bool, bcrypt_rounds: int) -> int:
    # Avoid shell history leakage: always prompt.
    password = getpass("Enter password (input hidden): ")
    if algo == "sha256":
        h = sha256_hash(password)
        payload = {"algorithm": "sha256", "hash": h}
    elif algo == "bcrypt":
        h = bcrypt_hash(password, rounds=bcrypt_rounds)
        payload = {"algorithm": "bcrypt", "hash": h, "bcrypt_rounds": bcrypt_rounds}
    else:
        print("Error: unsupported algorithm. Use sha256 or bcrypt.", file=sys.stderr)
        return 2

    if json_out:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Algorithm: {payload['algorithm']}")
        if algo == "bcrypt":
            print(f"bcrypt rounds: {payload['bcrypt_rounds']}")
        print(f"Hash: {payload['hash']}")
    return 0


def cmd_email(email: str, *, json_out: bool) -> int:
    try:
        masked = mask_email(email)
        payload = {"email": email.strip(), "masked": masked}
        if json_out:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Masked email: {masked}")
        return 0
    except UserInputError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


def interactive() -> int:
    while True:
        print("")
        print("IP & Data Security Tool")
        print("1) IP validation + ASN lookup (public IPs only)")
        print("2) Password hashing (local)")
        print("3) Email masking")
        print("4) Exit")
        choice = (input("Select an option (1-4): ") or "").strip()

        if choice == "1":
            ip_str = input("Enter an IPv4/IPv6 address: ").strip()
            _ = cmd_ip(ip_str, lookup=True, json_out=False)
        elif choice == "2":
            algo = (input("Hash algorithm (sha256/bcrypt) [sha256]: ").strip().lower() or "sha256")
            rounds = 12
            if algo == "bcrypt":
                r = (input("bcrypt rounds [12]: ").strip() or "12")
                try:
                    rounds = max(4, min(20, int(r)))
                except Exception:
                    rounds = 12
            _ = cmd_hash(algo=algo, json_out=False, bcrypt_rounds=rounds)
        elif choice == "3":
            email = input("Enter an email address: ").strip()
            _ = cmd_email(email, json_out=False)
        elif choice == "4":
            return 0
        else:
            print("Invalid selection.")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="IP & Data Security Tool (no geolocation; local hashing)")
    ap.add_argument("--json", action="store_true", help="Output JSON (for scripting).")
    sub = ap.add_subparsers(dest="cmd", required=False)

    ip_p = sub.add_parser("ip", help="Validate IP and (optionally) fetch ASN/org metadata")
    ip_p.add_argument("ip", help="IPv4 or IPv6 address")
    ip_p.add_argument(
        "--no-lookup",
        action="store_true",
        help="Skip ASN lookup (validation only).",
    )

    hash_p = sub.add_parser("hash", help="Hash a password locally (prompts input)")
    hash_p.add_argument("--algo", choices=("sha256", "bcrypt"), default="sha256", help="Hash algorithm")
    hash_p.add_argument("--bcrypt-rounds", type=int, default=12, help="bcrypt cost (if using bcrypt)")

    email_p = sub.add_parser("email", help="Validate and mask an email address")
    email_p.add_argument("email", help="Email address to mask")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    if not args.cmd:
        return interactive()

    if args.cmd == "ip":
        return cmd_ip(args.ip, lookup=not bool(args.no_lookup), json_out=bool(args.json))
    if args.cmd == "hash":
        rounds = int(getattr(args, "bcrypt_rounds", 12))
        rounds = max(4, min(20, rounds))
        return cmd_hash(algo=str(args.algo), json_out=bool(args.json), bcrypt_rounds=rounds)
    if args.cmd == "email":
        return cmd_email(str(args.email), json_out=bool(args.json))

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

