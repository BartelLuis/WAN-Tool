"""Verwaltung von Mandanten und Benutzern sowie Einsicht in das Audit-Log."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms
from app.database import get_db
from app.deps import Administrator, Verwalter, sichtbare_mandanten
from app.models import AuditEintrag, Benutzer, Mandant, MandantArt, Rolle
from app.security import hash_passwort, protokolliere
from app.templating import templates

router = APIRouter(prefix="/verwaltung", tags=["Verwaltung"])


def _startpasswort() -> str:
    """Zufaelliges Erstpasswort; muss bei der ersten Anmeldung gewechselt werden."""
    zeichen = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(zeichen) for _ in range(10)) + secrets.choice("!?#%+-")


# --------------------------------------------------------------------- Mandanten


@router.get("/mandanten", response_class=HTMLResponse)
def mandanten(request: Request, verwalter: Verwalter, db: Session = Depends(get_db)):
    stmt = select(Mandant).order_by(Mandant.name)
    if not verwalter.ist_admin:
        stmt = stmt.where(Mandant.id == verwalter.mandant_id)
    return templates.TemplateResponse(
        request,
        "verwaltung/mandanten.html",
        {"mandanten": list(db.scalars(stmt))},
    )


@router.post("/mandanten/speichern")
def mandant_speichern(
    request: Request,
    admin: Administrator,
    db: Session = Depends(get_db),
    mandant_id: str = Form(""),
    name: str = Form(...),
    kennzeichen: str = Form(...),
    art: str = Form(MandantArt.SONSTIGE.value),
    uebergeordnet_id: str = Form(""),
    aktiv: str = Form(""),
    notizen: str = Form(""),
):
    mid = forms.to_int(mandant_id)
    mandant = db.get(Mandant, mid) if mid else Mandant()
    if mid and mandant is None:
        raise HTTPException(status_code=404, detail="Mandant nicht gefunden.")

    uebergeordnet = forms.to_int(uebergeordnet_id)
    if uebergeordnet and mid and uebergeordnet in mandant.nachfahren_ids():
        raise HTTPException(
            status_code=400,
            detail="Der uebergeordnete Mandant darf nicht unterhalb dieses Mandanten liegen.",
        )

    mandant.name = name.strip()
    mandant.kennzeichen = kennzeichen.strip().upper()
    mandant.art = forms.to_enum(MandantArt, art, MandantArt.SONSTIGE)
    mandant.uebergeordnet_id = uebergeordnet
    mandant.aktiv = bool(aktiv)
    mandant.notizen = forms.to_str(notizen)

    db.add(mandant)
    db.flush()
    protokolliere(
        db,
        request,
        admin,
        "mandant_gespeichert",
        "Mandant",
        mandant.id,
        mandant.name,
        mandant_id=mandant.id,
        mandant_name=mandant.name,
    )
    db.commit()
    return RedirectResponse("/verwaltung/mandanten", status_code=303)


# ---------------------------------------------------------------------- Benutzer


@router.get("/benutzer", response_class=HTMLResponse)
def benutzer_liste(request: Request, verwalter: Verwalter, db: Session = Depends(get_db)):
    stmt = select(Benutzer).order_by(Benutzer.benutzername)
    if not verwalter.ist_admin:
        stmt = stmt.where(Benutzer.mandant_id == verwalter.mandant_id)
    mandanten_stmt = select(Mandant).where(Mandant.aktiv.is_(True)).order_by(Mandant.name)
    if not verwalter.ist_admin:
        mandanten_stmt = mandanten_stmt.where(Mandant.id == verwalter.mandant_id)
    # Einmalanzeige: das Erstpasswort verlaesst die Sitzung nicht ueber die URL.
    hinweis = request.session.pop("startpasswort", None)
    return templates.TemplateResponse(
        request,
        "verwaltung/benutzer.html",
        {
            "konten": list(db.scalars(stmt)),
            "mandanten": list(db.scalars(mandanten_stmt)),
            "startpasswort": hinweis,
        },
    )


def _rolle_pruefen(verwalter: Benutzer, rolle: Rolle, mandant_id: int) -> None:
    if verwalter.ist_admin:
        return
    if rolle == Rolle.ADMIN:
        raise HTTPException(
            status_code=403, detail="Administratorrolle darf nicht vergeben werden."
        )
    if mandant_id != verwalter.mandant_id:
        raise HTTPException(status_code=403, detail="Nur Konten des eigenen Mandanten.")


@router.post("/benutzer/speichern")
def benutzer_speichern(
    request: Request,
    verwalter: Verwalter,
    db: Session = Depends(get_db),
    benutzer_id: str = Form(""),
    benutzername: str = Form(...),
    name: str = Form(...),
    email: str = Form(""),
    rolle: str = Form(Rolle.LESER.value),
    mandant_id: str = Form(...),
    sieht_untergeordnete: str = Form(""),
    aktiv: str = Form(""),
):
    bid = forms.to_int(benutzer_id)
    ziel_mandant = forms.to_int(mandant_id)
    ziel_rolle = forms.to_enum(Rolle, rolle, Rolle.LESER)
    if ziel_mandant is None:
        raise HTTPException(status_code=400, detail="Mandant ist erforderlich.")
    _rolle_pruefen(verwalter, ziel_rolle, ziel_mandant)

    konto = db.get(Benutzer, bid) if bid else Benutzer()
    if bid:
        if konto is None:
            raise HTTPException(status_code=404, detail="Konto nicht gefunden.")
        _rolle_pruefen(verwalter, konto.rolle, konto.mandant_id)

    startpasswort = None
    if not bid:
        startpasswort = _startpasswort()
        konto.passwort_hash = hash_passwort(startpasswort)
        konto.passwort_aendern = True

    konto.benutzername = benutzername.strip().lower()
    konto.name = name.strip()
    konto.email = forms.to_str(email)
    konto.rolle = ziel_rolle
    konto.mandant_id = ziel_mandant
    konto.sieht_untergeordnete = bool(sieht_untergeordnete)
    konto.aktiv = bool(aktiv)

    if konto.id == verwalter.id and not konto.aktiv:
        raise HTTPException(
            status_code=400, detail="Das eigene Konto kann nicht deaktiviert werden."
        )

    db.add(konto)
    db.flush()
    protokolliere(
        db,
        request,
        verwalter,
        "benutzer_gespeichert",
        "Benutzer",
        konto.id,
        f"{konto.benutzername} ({konto.rolle.value})",
    )
    db.commit()

    if startpasswort:
        request.session["startpasswort"] = {
            "konto": konto.benutzername,
            "passwort": startpasswort,
        }
    return RedirectResponse("/verwaltung/benutzer", status_code=303)


@router.post("/benutzer/{konto_id}/passwort-zuruecksetzen")
def passwort_zuruecksetzen(
    konto_id: int,
    request: Request,
    verwalter: Verwalter,
    db: Session = Depends(get_db),
):
    konto = db.get(Benutzer, konto_id)
    if konto is None:
        raise HTTPException(status_code=404, detail="Konto nicht gefunden.")
    _rolle_pruefen(verwalter, konto.rolle, konto.mandant_id)

    neues = _startpasswort()
    konto.passwort_hash = hash_passwort(neues)
    konto.passwort_aendern = True
    konto.fehlversuche = 0
    konto.gesperrt_bis = None
    protokolliere(
        db, request, verwalter, "passwort_zurueckgesetzt", "Benutzer", konto.id, konto.benutzername
    )
    db.commit()
    request.session["startpasswort"] = {"konto": konto.benutzername, "passwort": neues}
    return RedirectResponse("/verwaltung/benutzer", status_code=303)


# --------------------------------------------------------------------- Audit-Log


@router.get("/audit", response_class=HTMLResponse)
def audit(
    request: Request,
    verwalter: Verwalter,
    db: Session = Depends(get_db),
    aktion: str = "",
    seite: int = 1,
):
    pro_seite = 100
    seite = max(1, seite)
    stmt = select(AuditEintrag).order_by(AuditEintrag.id.desc())
    ids = sichtbare_mandanten(db, verwalter)
    if ids is not None:
        stmt = stmt.where(AuditEintrag.mandant_id.in_(ids))
    if begriff := forms.to_str(aktion):
        stmt = stmt.where(AuditEintrag.aktion.like(f"%{begriff}%"))

    eintraege = list(db.scalars(stmt.offset((seite - 1) * pro_seite).limit(pro_seite + 1)))
    weitere = len(eintraege) > pro_seite
    return templates.TemplateResponse(
        request,
        "verwaltung/audit.html",
        {
            "eintraege": eintraege[:pro_seite],
            "seite": seite,
            "weitere": weitere,
            "filter": {"aktion": aktion},
        },
    )
