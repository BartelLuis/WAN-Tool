from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms
from app.database import get_db
from app.models import Standort
from app.templating import templates
from app.routers.common import hole_oder_404

router = APIRouter(prefix="/standorte", tags=["Standorte"])


@router.get("", response_class=HTMLResponse)
def liste(request: Request, db: Session = Depends(get_db)):
    standorte = db.scalars(select(Standort).order_by(Standort.name)).all()
    return templates.TemplateResponse(
        request, "standorte/liste.html", {"standorte": standorte}
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request):
    return templates.TemplateResponse(request, "standorte/formular.html", {"standort": None})


@router.get("/{standort_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(standort_id: int, request: Request, db: Session = Depends(get_db)):
    standort = hole_oder_404(db, Standort, standort_id)
    return templates.TemplateResponse(
        request, "standorte/formular.html", {"standort": standort}
    )


@router.post("/speichern")
def speichern(
    db: Session = Depends(get_db),
    standort_id: str = Form(""),
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
    sid = forms.to_int(standort_id)
    standort = hole_oder_404(db, Standort, sid) if sid else Standort()

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
    db.commit()
    return RedirectResponse("/standorte", status_code=303)


@router.post("/{standort_id}/loeschen")
def loeschen(standort_id: int, db: Session = Depends(get_db)):
    db.delete(hole_oder_404(db, Standort, standort_id))
    db.commit()
    return RedirectResponse("/standorte", status_code=303)
