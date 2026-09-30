"""Middleware fuer Sicherheits-Header, Sitzungspruefung und CSRF-Schutz."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.database import SessionLocal
from app.models import Benutzer
from app.security import csrf_gueltig, neues_csrf_token

logger = logging.getLogger("wantool.sicherheit")

# Ohne externe Quellen: saemtliche Assets werden lokal ausgeliefert.
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)

OEFFENTLICHE_PFADE = ("/login", "/static", "/health")
PASSWORT_AUSNAHMEN = ("/passwort", "/abmelden", "/static", "/health")
SICHERE_METHODEN = frozenset({"GET", "HEAD", "OPTIONS"})


def _beginnt_mit(pfad: str, praefixe: tuple[str, ...]) -> bool:
    return any(pfad == p or pfad.startswith(p + "/") for p in praefixe)


def _will_json(request: Request) -> bool:
    return request.url.path.startswith("/api")


class SicherheitsHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        antwort: Response = await call_next(request)
        antwort.headers["Content-Security-Policy"] = CSP
        antwort.headers["X-Content-Type-Options"] = "nosniff"
        antwort.headers["X-Frame-Options"] = "DENY"
        antwort.headers["Referrer-Policy"] = "no-referrer"
        antwort.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )
        antwort.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        antwort.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        antwort.headers.setdefault("Cache-Control", "no-store")
        if settings.cookie_secure:
            antwort.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return antwort


class AuthentifizierungsMiddleware(BaseHTTPMiddleware):
    """Erzwingt Anmeldung, Sitzungsdauer, CSRF-Schutz und faelligen Passwortwechsel."""

    async def dispatch(self, request: Request, call_next):
        sitzung = request.session
        jetzt = datetime.now(UTC).timestamp()
        pfad = request.url.path

        self._sitzung_pruefen(sitzung, jetzt)
        if sitzung.get("benutzer_id") is not None and not self._benutzer_laden(sitzung):
            sitzung.clear()

        angemeldet = sitzung.get("benutzer_id") is not None
        if not angemeldet and not _beginnt_mit(pfad, OEFFENTLICHE_PFADE):
            if _will_json(request):
                return JSONResponse({"detail": "Nicht angemeldet."}, status_code=401)
            return RedirectResponse("/login", status_code=303)

        if request.method not in SICHERE_METHODEN:
            # Body puffern, damit die Route ihn nach der Pruefung erneut lesen kann.
            koerper = await request.body()

            async def _receive() -> dict:
                return {"type": "http.request", "body": koerper, "more_body": False}

            request._receive = _receive
            formular = await request.form()
            if not csrf_gueltig(sitzung.get("csrf"), formular.get("csrf_token")):
                logger.warning("CSRF-Pruefung fehlgeschlagen: %s %s", request.method, pfad)
                return JSONResponse(
                    {"detail": "Sicherheitstoken ungueltig. Bitte Seite neu laden."},
                    status_code=403,
                )

        if not sitzung.get("csrf"):
            sitzung["csrf"] = neues_csrf_token()

        if (
            angemeldet
            and sitzung.get("passwort_aendern")
            and not _beginnt_mit(pfad, PASSWORT_AUSNAHMEN)
        ):
            if _will_json(request):
                return JSONResponse({"detail": "Passwortaenderung erforderlich."}, status_code=403)
            return RedirectResponse("/passwort", status_code=303)

        return await call_next(request)

    @staticmethod
    def _sitzung_pruefen(sitzung: dict, jetzt: float) -> None:
        if sitzung.get("benutzer_id") is None:
            return
        beginn = sitzung.get("beginn", 0)
        aktivitaet = sitzung.get("aktivitaet", 0)
        if (
            jetzt - aktivitaet > settings.session_leerlauf_minuten * 60
            or jetzt - beginn > settings.session_maximal_minuten * 60
        ):
            sitzung.clear()
        else:
            sitzung["aktivitaet"] = jetzt

    @staticmethod
    def _benutzer_laden(sitzung: dict) -> bool:
        """Prueft das Konto bei jedem Zugriff und haelt die Anzeigedaten aktuell.

        Gesperrte Konten verlieren ihre Sitzung damit sofort, nicht erst beim Ablauf.
        """
        db = SessionLocal()
        try:
            benutzer = db.get(Benutzer, sitzung["benutzer_id"])
            if not benutzer or not benutzer.aktiv or not benutzer.mandant.aktiv:
                return False
            sitzung["anzeige"] = {
                "name": benutzer.name,
                "benutzername": benutzer.benutzername,
                "rolle": benutzer.rolle.value,
                "mandant": benutzer.mandant.anzeigename,
                "ist_admin": benutzer.ist_admin,
                "darf_schreiben": benutzer.darf_schreiben,
                "darf_verwalten": benutzer.darf_verwalten,
                "sieht_untergeordnete": benutzer.sieht_untergeordnete,
            }
            return True
        finally:
            db.close()
