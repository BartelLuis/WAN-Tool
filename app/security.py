"""Passwort-Hashing, Passwortregeln, CSRF-Token und Audit-Protokoll."""

from __future__ import annotations

import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditEintrag, Benutzer

# Parameter oberhalb der Argon2-Referenzwerte, vgl. BSI TR-02102-1.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)


def hash_passwort(passwort: str) -> str:
    return _hasher.hash(passwort)


def passwort_pruefen(hash_wert: str, passwort: str) -> bool:
    try:
        return _hasher.verify(hash_wert, passwort)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def hash_veraltet(hash_wert: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hash_wert)
    except (InvalidHashError, ValueError):
        return True


def passwort_regeln(passwort: str) -> list[str]:
    """Gibt die verletzten Passwortregeln zurueck; leere Liste bedeutet gueltig."""
    fehler: list[str] = []
    if len(passwort) < settings.passwort_mindestlaenge:
        fehler.append(f"mindestens {settings.passwort_mindestlaenge} Zeichen")
    if not re.search(r"[a-z]", passwort):
        fehler.append("mindestens ein Kleinbuchstabe")
    if not re.search(r"[A-Z]", passwort):
        fehler.append("mindestens ein Grossbuchstabe")
    if not re.search(r"\d", passwort):
        fehler.append("mindestens eine Ziffer")
    if not re.search(r"[^\w\s]", passwort):
        fehler.append("mindestens ein Sonderzeichen")
    return fehler


def neues_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_gueltig(erwartet: str | None, uebergeben: str | None) -> bool:
    if not erwartet or not uebergeben:
        return False
    return hmac.compare_digest(erwartet, uebergeben)


def client_ip(request: Request) -> str | None:
    """Client-Adresse; hinter einem Reverse Proxy aus X-Forwarded-For."""
    if settings.vertraue_proxy_header:
        weitergeleitet = request.headers.get("x-forwarded-for")
        if weitergeleitet:
            return weitergeleitet.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def protokolliere(
    db: Session,
    request: Request,
    benutzer: Benutzer | None,
    aktion: str,
    objekt_typ: str,
    objekt_id: int | None = None,
    beschreibung: str | None = None,
    mandant_id: int | None = None,
    mandant_name: str | None = None,
) -> None:
    if benutzer is not None:
        mandant_id = mandant_id if mandant_id is not None else benutzer.mandant_id
        mandant_name = mandant_name or (benutzer.mandant.name if benutzer.mandant else None)
    db.add(
        AuditEintrag(
            benutzername=benutzer.benutzername if benutzer else "anonym",
            mandant_id=mandant_id,
            mandant_name=mandant_name,
            aktion=aktion,
            objekt_typ=objekt_typ,
            objekt_id=objekt_id,
            beschreibung=(beschreibung or "")[:500] or None,
            ip=client_ip(request),
        )
    )


def ist_gesperrt(benutzer: Benutzer) -> bool:
    return benutzer.gesperrt_bis is not None and benutzer.gesperrt_bis > datetime.now(UTC).replace(
        tzinfo=None
    )


def fehlversuch_zaehlen(benutzer: Benutzer) -> None:
    benutzer.fehlversuche += 1
    if benutzer.fehlversuche >= settings.max_fehlversuche:
        benutzer.gesperrt_bis = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            minutes=settings.sperrdauer_minuten
        )
        benutzer.fehlversuche = 0
