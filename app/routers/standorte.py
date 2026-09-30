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
from app.models import Standort
from app.security import protokolliere
from app.templating import templates

router = APIRouter(prefix="/standorte", tags=["Standorte"])


@router.get("", response_class=HTMLResponse)
def liste(request: Request, benutzer: Angemeldet, db: Session = Depends(get_db)):
    stmt = beschraenke(select(Standort).order_by(Standort.name), Standort, db, benutzer)
    return templates.TemplateResponse(
        request, "standorte/liste.html", {"standorte": list(db.scalars(stmt))}
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request, bearbeiter: Bearbeiter, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "standorte/formular.html",
        {"standort": None, "mandanten": auswahl_mandanten(db, bearbeiter)},
    )


@router.get("/{standort_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(
    standort_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    standort = hole_bearbeitbar(db, Standort, standort_id, bearbeiter)
    return templates.TemplateResponse(
        request,
        "standorte/formular.html",
        {"standort": standort, "mandanten": auswahl_mandanten(db, bearbeiter)},
    )


@router.post("/speichern")
def speichern(
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
    standort_id: str = Form(""),
    mandant_id: str = Form(...),
    name: str = Form(...),
    kurzzeichen: str = Form(""),
    strasse: str = Form(""),
    plz: str = Form(""),
    ort: str = Form(""),
    land: str = Form("Deutschland"),
    ansprechpartner: str = Form(""),
    telefon: str = Form(""),
    notizen: str = Form(""),
):
    ziel_mandant = forms.to_int(mandant_id)
    if ziel_mandant is None or not darf_bearbeiten(db, bearbeiter, ziel_mandant):
        raise HTTPException(status_code=403, detail="Unzulaessiger Mandant.")

    sid = forms.to_int(standort_id)
    standort = hole_bearbeitbar(db, Standort, sid, bearbeiter) if sid else Standort()

    standort.mandant_id = ziel_mandant
    standort.name = name.strip()
    standort.kurzzeichen = forms.to_str(kurzzeichen)
    standort.strasse = forms.to_str(strasse)
    standort.plz = forms.to_str(plz)
    standort.ort = forms.to_str(ort)
    standort.land = forms.to_str(land) or "Deutschland"
    standort.ansprechpartner = forms.to_str(ansprechpartner)
    standort.telefon = forms.to_str(telefon)
    standort.notizen = forms.to_str(notizen)

    db.add(standort)
    db.flush()
    protokolliere(
        db,
        request,
        bearbeiter,
        "gespeichert",
        "Standort",
        standort.id,
        standort.name,
        mandant_id=ziel_mandant,
    )
    db.commit()
    return RedirectResponse("/standorte", status_code=303)


@router.post("/{standort_id}/loeschen")
def loeschen(
    standort_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    standort = hole_bearbeitbar(db, Standort, standort_id, bearbeiter)
    protokolliere(
        db,
        request,
        bearbeiter,
        "geloescht",
        "Standort",
        standort.id,
        standort.name,
        mandant_id=standort.mandant_id,
    )
    db.delete(standort)
    db.commit()
    return RedirectResponse("/standorte", status_code=303)
