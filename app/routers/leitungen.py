from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import forms
from app.database import get_db
from app.models import Leitung, Leitungsart, LeitungStatus, Provider, Standort, Technologie
from app.routers.common import hole_oder_404
from app.services import leitungen_csv
from app.templating import templates

router = APIRouter(prefix="/leitungen", tags=["Leitungen"])


def _basisdaten(db: Session) -> dict:
    return {
        "standorte": db.scalars(select(Standort).order_by(Standort.name)).all(),
        "providerliste": db.scalars(select(Provider).order_by(Provider.name)).all(),
    }


def _gefiltert(db: Session, art: str, status: str, provider_id: str, suche: str):
    stmt = select(Leitung).order_by(Leitung.bezeichnung)
    art_enum = forms.to_enum(Leitungsart, art)
    status_enum = forms.to_enum(LeitungStatus, status)
    pid = forms.to_int(provider_id)
    begriff = forms.to_str(suche)

    if art_enum:
        stmt = stmt.where(Leitung.art == art_enum)
    if status_enum:
        stmt = stmt.where(Leitung.status == status_enum)
    if pid:
        stmt = stmt.where(Leitung.provider_id == pid)
    if begriff:
        muster = f"%{begriff}%"
        stmt = stmt.where(
            or_(
                Leitung.bezeichnung.like(muster),
                Leitung.circuit_id.like(muster),
                Leitung.vertragsnummer.like(muster),
                Leitung.anschlusskennung.like(muster),
                Leitung.rufnummernblock.like(muster),
            )
        )
    return db.scalars(stmt).all()


@router.get("", response_class=HTMLResponse)
def liste(
    request: Request,
    db: Session = Depends(get_db),
    art: str = "",
    status: str = "",
    provider_id: str = "",
    suche: str = "",
):
    leitungen = _gefiltert(db, art, status, provider_id, suche)
    return templates.TemplateResponse(
        request,
        "leitungen/liste.html",
        {
            "leitungen": leitungen,
            "filter": {"art": art, "status": status, "provider_id": provider_id, "suche": suche},
            **_basisdaten(db),
        },
    )


@router.get("/export.csv")
def export(
    db: Session = Depends(get_db),
    art: str = "",
    status: str = "",
    provider_id: str = "",
    suche: str = "",
):
    leitungen = _gefiltert(db, art, status, provider_id, suche)
    return StreamingResponse(
        leitungen_csv(leitungen),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leitungen.csv"'},
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "leitungen/formular.html", {"leitung": None, **_basisdaten(db)}
    )


@router.get("/{leitung_id}", response_class=HTMLResponse)
def detail(leitung_id: int, request: Request, db: Session = Depends(get_db)):
    leitung = hole_oder_404(db, Leitung, leitung_id)
    return templates.TemplateResponse(request, "leitungen/detail.html", {"leitung": leitung})


@router.get("/{leitung_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(leitung_id: int, request: Request, db: Session = Depends(get_db)):
    leitung = hole_oder_404(db, Leitung, leitung_id)
    return templates.TemplateResponse(
        request, "leitungen/formular.html", {"leitung": leitung, **_basisdaten(db)}
    )


@router.post("/speichern")
def speichern(
    db: Session = Depends(get_db),
    leitung_id: str = Form(""),
    bezeichnung: str = Form(...),
    art: str = Form(Leitungsart.WAN.value),
    technologie: str = Form(Technologie.SONSTIGE.value),
    status: str = Form(LeitungStatus.GEPLANT.value),
    provider_id: str = Form(""),
    standort_a_id: str = Form(""),
    standort_b_id: str = Form(""),
    bandbreite_down_mbit: str = Form(""),
    bandbreite_up_mbit: str = Form(""),
    sprachkanaele: str = Form(""),
    rufnummernblock: str = Form(""),
    circuit_id: str = Form(""),
    anschlusskennung: str = Form(""),
    ip_transfernetz: str = Form(""),
    ip_lan_netz: str = Form(""),
    router_typ: str = Form(""),
    sla: str = Form(""),
    vertragsnummer: str = Form(""),
    kosten_monatlich: str = Form(""),
    kosten_einmalig: str = Form(""),
    vertragsbeginn: str = Form(""),
    vertragsende: str = Form(""),
    kuendigungsfrist_monate: str = Form(""),
    verlaengerung_monate: str = Form(""),
    notizen: str = Form(""),
):
    lid = forms.to_int(leitung_id)
    leitung = hole_oder_404(db, Leitung, lid) if lid else Leitung()

    leitung.bezeichnung = bezeichnung.strip()
    leitung.art = forms.to_enum(Leitungsart, art, Leitungsart.WAN)
    leitung.technologie = forms.to_enum(Technologie, technologie, Technologie.SONSTIGE)
    leitung.status = forms.to_enum(LeitungStatus, status, LeitungStatus.GEPLANT)
    leitung.provider_id = forms.to_int(provider_id)
    leitung.standort_a_id = forms.to_int(standort_a_id)
    leitung.standort_b_id = forms.to_int(standort_b_id)
    leitung.bandbreite_down_mbit = forms.to_int(bandbreite_down_mbit)
    leitung.bandbreite_up_mbit = forms.to_int(bandbreite_up_mbit)
    leitung.sprachkanaele = forms.to_int(sprachkanaele)
    leitung.rufnummernblock = forms.to_str(rufnummernblock)
    leitung.circuit_id = forms.to_str(circuit_id)
    leitung.anschlusskennung = forms.to_str(anschlusskennung)
    leitung.ip_transfernetz = forms.to_str(ip_transfernetz)
    leitung.ip_lan_netz = forms.to_str(ip_lan_netz)
    leitung.router_typ = forms.to_str(router_typ)
    leitung.sla = forms.to_str(sla)
    leitung.vertragsnummer = forms.to_str(vertragsnummer)
    leitung.kosten_monatlich = forms.to_decimal(kosten_monatlich)
    leitung.kosten_einmalig = forms.to_decimal(kosten_einmalig)
    leitung.vertragsbeginn = forms.to_date(vertragsbeginn)
    leitung.vertragsende = forms.to_date(vertragsende)
    leitung.kuendigungsfrist_monate = forms.to_int(kuendigungsfrist_monate)
    leitung.verlaengerung_monate = forms.to_int(verlaengerung_monate)
    leitung.notizen = forms.to_str(notizen)

    db.add(leitung)
    db.commit()
    return RedirectResponse(f"/leitungen/{leitung.id}", status_code=303)


@router.post("/{leitung_id}/loeschen")
def loeschen(leitung_id: int, db: Session = Depends(get_db)):
    db.delete(hole_oder_404(db, Leitung, leitung_id))
    db.commit()
    return RedirectResponse("/leitungen", status_code=303)
