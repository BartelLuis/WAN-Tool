from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms
from app.database import get_db
from app.deps import (
    Angemeldet,
    Bearbeiter,
    auswahl_mandanten,
    beschraenke,
    darf_bearbeiten,
    hole_bearbeitbar,
)
from app.models import Provider
from app.security import protokolliere
from app.templating import templates

router = APIRouter(prefix="/provider", tags=["Provider"])


@router.get("", response_class=HTMLResponse)
def liste(request: Request, benutzer: Angemeldet, db: Session = Depends(get_db)):
    stmt = beschraenke(select(Provider).order_by(Provider.name), Provider, db, benutzer)
    return templates.TemplateResponse(
        request, "provider/liste.html", {"provider": list(db.scalars(stmt))}
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request, bearbeiter: Bearbeiter, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "provider/formular.html",
        {"eintrag": None, "mandanten": auswahl_mandanten(db, bearbeiter)},
    )


@router.get("/{provider_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(
    provider_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    eintrag = hole_bearbeitbar(db, Provider, provider_id, bearbeiter)
    return templates.TemplateResponse(
        request,
        "provider/formular.html",
        {"eintrag": eintrag, "mandanten": auswahl_mandanten(db, bearbeiter)},
    )


@router.post("/speichern")
def speichern(
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
    provider_id: str = Form(""),
    mandant_id: str = Form(...),
    name: str = Form(...),
    kundennummer: str = Form(""),
    ansprechpartner: str = Form(""),
    email: str = Form(""),
    telefon: str = Form(""),
    webseite: str = Form(""),
    stoerungshotline: str = Form(""),
    notizen: str = Form(""),
):
    ziel_mandant = forms.to_int(mandant_id)
    if ziel_mandant is None or not darf_bearbeiten(db, bearbeiter, ziel_mandant):
        raise HTTPException(status_code=403, detail="Unzulaessiger Mandant.")

    pid = forms.to_int(provider_id)
    eintrag = hole_bearbeitbar(db, Provider, pid, bearbeiter) if pid else Provider()

    eintrag.mandant_id = ziel_mandant
    eintrag.name = name.strip()
    eintrag.kundennummer = forms.to_str(kundennummer)
    eintrag.ansprechpartner = forms.to_str(ansprechpartner)
    eintrag.email = forms.to_str(email)
    eintrag.telefon = forms.to_str(telefon)
    eintrag.webseite = forms.to_str(webseite)
    eintrag.stoerungshotline = forms.to_str(stoerungshotline)
    eintrag.notizen = forms.to_str(notizen)

    db.add(eintrag)
    db.flush()
    protokolliere(
        db,
        request,
        bearbeiter,
        "gespeichert",
        "Provider",
        eintrag.id,
        eintrag.name,
        mandant_id=ziel_mandant,
    )
    db.commit()
    return RedirectResponse("/provider", status_code=303)


@router.post("/{provider_id}/loeschen")
def loeschen(
    provider_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    eintrag = hole_bearbeitbar(db, Provider, provider_id, bearbeiter)
    protokolliere(
        db,
        request,
        bearbeiter,
        "geloescht",
        "Provider",
        eintrag.id,
        eintrag.name,
        mandant_id=eintrag.mandant_id,
    )
    db.delete(eintrag)
    db.commit()
    return RedirectResponse("/provider", status_code=303)
