"""Anmeldung, Abmeldung und Passwortwechsel."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Angemeldet
from app.models import Benutzer
from app.security import (
    fehlversuch_zaehlen,
    hash_passwort,
    hash_veraltet,
    ist_gesperrt,
    passwort_pruefen,
    passwort_regeln,
    protokolliere,
)
from app.templating import templates

router = APIRouter(tags=["Anmeldung"])

# Einheitliche Meldung, damit gueltige Benutzernamen nicht erkennbar werden.
FEHLER_ANMELDUNG = "Benutzername oder Passwort ist falsch."


def _jetzt() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/login", response_class=HTMLResponse)
def login_formular(request: Request):
    if request.session.get("benutzer_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"fehler": None})


@router.post("/login")
def anmelden(
    request: Request,
    db: Session = Depends(get_db),
    benutzername: str = Form(...),
    passwort: str = Form(...),
):
    def abweisen(grund: str) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", {"fehler": grund}, status_code=401)

    benutzer = db.scalar(select(Benutzer).where(Benutzer.benutzername == benutzername.strip()))

    if benutzer is None:
        # Dummy-Verifikation gleicht die Antwortzeit an und verhindert Benutzer-Enumeration.
        passwort_pruefen("$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAA$AAAAAAAAAAA", passwort)
        protokolliere(db, request, None, "anmeldung_fehlgeschlagen", "Benutzer", None, benutzername)
        db.commit()
        return abweisen(FEHLER_ANMELDUNG)

    if ist_gesperrt(benutzer):
        protokolliere(db, request, benutzer, "anmeldung_gesperrt", "Benutzer", benutzer.id)
        db.commit()
        return abweisen("Das Konto ist voruebergehend gesperrt. Bitte spaeter erneut versuchen.")

    if not benutzer.aktiv or not benutzer.mandant.aktiv:
        protokolliere(db, request, benutzer, "anmeldung_inaktiv", "Benutzer", benutzer.id)
        db.commit()
        return abweisen(FEHLER_ANMELDUNG)

    if not passwort_pruefen(benutzer.passwort_hash, passwort):
        fehlversuch_zaehlen(benutzer)
        protokolliere(db, request, benutzer, "anmeldung_fehlgeschlagen", "Benutzer", benutzer.id)
        db.commit()
        return abweisen(FEHLER_ANMELDUNG)

    if hash_veraltet(benutzer.passwort_hash):
        benutzer.passwort_hash = hash_passwort(passwort)

    benutzer.fehlversuche = 0
    benutzer.gesperrt_bis = None
    benutzer.letzter_login = _jetzt()
    protokolliere(db, request, benutzer, "anmeldung", "Benutzer", benutzer.id)
    db.commit()

    # Neue Sitzungskennung nach erfolgreicher Anmeldung (Schutz vor Session Fixation).
    request.session.clear()
    jetzt = datetime.now(UTC).timestamp()
    request.session.update(
        {
            "benutzer_id": benutzer.id,
            "beginn": jetzt,
            "aktivitaet": jetzt,
            "passwort_aendern": benutzer.passwort_aendern,
        }
    )
    ziel = "/passwort" if benutzer.passwort_aendern else "/"
    return RedirectResponse(ziel, status_code=303)


@router.post("/abmelden")
def abmelden(request: Request, db: Session = Depends(get_db)):
    benutzer_id = request.session.get("benutzer_id")
    if benutzer_id:
        benutzer = db.get(Benutzer, benutzer_id)
        protokolliere(db, request, benutzer, "abmeldung", "Benutzer", benutzer_id)
        db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/passwort", response_class=HTMLResponse)
def passwort_formular(request: Request, benutzer: Angemeldet):
    return templates.TemplateResponse(
        request,
        "passwort.html",
        {"fehler": None, "erzwungen": benutzer.passwort_aendern},
    )


@router.post("/passwort")
def passwort_aendern(
    request: Request,
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
    altes_passwort: str = Form(...),
    neues_passwort: str = Form(...),
    wiederholung: str = Form(...),
):
    def abweisen(grund: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "passwort.html",
            {"fehler": grund, "erzwungen": benutzer.passwort_aendern},
            status_code=400,
        )

    if not passwort_pruefen(benutzer.passwort_hash, altes_passwort):
        protokolliere(db, request, benutzer, "passwort_fehlversuch", "Benutzer", benutzer.id)
        db.commit()
        return abweisen("Das aktuelle Passwort ist falsch.")
    if neues_passwort != wiederholung:
        return abweisen("Die beiden neuen Passwoerter stimmen nicht ueberein.")
    if neues_passwort == altes_passwort:
        return abweisen("Das neue Passwort muss sich vom bisherigen unterscheiden.")
    if fehler := passwort_regeln(neues_passwort):
        return abweisen("Das Passwort erfuellt nicht die Vorgaben: " + ", ".join(fehler) + ".")

    benutzer.passwort_hash = hash_passwort(neues_passwort)
    benutzer.passwort_aendern = False
    benutzer.passwort_geaendert_am = _jetzt()
    protokolliere(db, request, benutzer, "passwort_geaendert", "Benutzer", benutzer.id)
    db.commit()

    request.session["passwort_aendern"] = False
    return RedirectResponse("/", status_code=303)
