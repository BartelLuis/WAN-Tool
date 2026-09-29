from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms
from app.database import get_db
from app.models import Provider
from app.routers.common import hole_oder_404
from app.templating import templates

router = APIRouter(prefix="/provider", tags=["Provider"])


@router.get("", response_class=HTMLResponse)
def liste(request: Request, db: Session = Depends(get_db)):
    provider = db.scalars(select(Provider).order_by(Provider.name)).all()
    return templates.TemplateResponse(request, "provider/liste.html", {"provider": provider})


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request):
    return templates.TemplateResponse(request, "provider/formular.html", {"eintrag": None})


@router.get("/{provider_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(provider_id: int, request: Request, db: Session = Depends(get_db)):
    eintrag = hole_oder_404(db, Provider, provider_id)
    return templates.TemplateResponse(request, "provider/formular.html", {"eintrag": eintrag})


@router.post("/speichern")
def speichern(
    db: Session = Depends(get_db),
    provider_id: str = Form(""),
    name: str = Form(...),
    kundennummer: str = Form(""),
    ansprechpartner: str = Form(""),
    email: str = Form(""),
    telefon: str = Form(""),
    webseite: str = Form(""),
    stoerungshotline: str = Form(""),
    notizen: str = Form(""),
):
    pid = forms.to_int(provider_id)
    eintrag = hole_oder_404(db, Provider, pid) if pid else Provider()

    eintrag.name = name.strip()
    eintrag.kundennummer = forms.to_str(kundennummer)
    eintrag.ansprechpartner = forms.to_str(ansprechpartner)
    eintrag.email = forms.to_str(email)
    eintrag.telefon = forms.to_str(telefon)
    eintrag.webseite = forms.to_str(webseite)
    eintrag.stoerungshotline = forms.to_str(stoerungshotline)
    eintrag.notizen = forms.to_str(notizen)

    db.add(eintrag)
    db.commit()
    return RedirectResponse("/provider", status_code=303)


@router.post("/{provider_id}/loeschen")
def loeschen(provider_id: int, db: Session = Depends(get_db)):
    db.delete(hole_oder_404(db, Provider, provider_id))
    db.commit()
    return RedirectResponse("/provider", status_code=303)
