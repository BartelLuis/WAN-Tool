from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms
from app.database import get_db
from app.models import (
    Angebot,
    AngebotStatus,
    Angebotsanfrage,
    AnfrageStatus,
    Leitungsart,
    Provider,
    Standort,
    Technologie,
)
from app.routers.common import hole_oder_404
from app.services import anfragetext, angebot_beauftragen
from app.templating import templates

router = APIRouter(prefix="/anfragen", tags=["Angebotsanfragen"])


def _basisdaten(db: Session) -> dict:
    return {
        "standorte": db.scalars(select(Standort).order_by(Standort.name)).all(),
        "providerliste": db.scalars(select(Provider).order_by(Provider.name)).all(),
    }


@router.get("", response_class=HTMLResponse)
def liste(request: Request, db: Session = Depends(get_db), status: str = ""):
    stmt = select(Angebotsanfrage).order_by(Angebotsanfrage.id.desc())
    status_enum = forms.to_enum(AnfrageStatus, status)
    if status_enum:
        stmt = stmt.where(Angebotsanfrage.status == status_enum)
    anfragen = db.scalars(stmt).all()
    return templates.TemplateResponse(
        request, "anfragen/liste.html", {"anfragen": anfragen, "filter": {"status": status}}
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "anfragen/formular.html", {"anfrage": None, **_basisdaten(db)}
    )


@router.get("/{anfrage_id}", response_class=HTMLResponse)
def detail(anfrage_id: int, request: Request, db: Session = Depends(get_db)):
    anfrage = hole_oder_404(db, Angebotsanfrage, anfrage_id)
    vergeben = {a.provider_id for a in anfrage.angebote}
    offene_provider = [
        p for p in db.scalars(select(Provider).order_by(Provider.name)) if p.id not in vergeben
    ]
    bestes = min(
        (a for a in anfrage.angebote if a.tco is not None),
        key=lambda a: a.tco,
        default=None,
    )
    return templates.TemplateResponse(
        request,
        "anfragen/detail.html",
        {
            "anfrage": anfrage,
            "offene_provider": offene_provider,
            "bestes_angebot": bestes,
            "anschreiben": anfragetext(anfrage),
        },
    )


@router.get("/{anfrage_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(anfrage_id: int, request: Request, db: Session = Depends(get_db)):
    anfrage = hole_oder_404(db, Angebotsanfrage, anfrage_id)
    return templates.TemplateResponse(
        request, "anfragen/formular.html", {"anfrage": anfrage, **_basisdaten(db)}
    )


@router.post("/speichern")
def speichern(
    db: Session = Depends(get_db),
    anfrage_id: str = Form(""),
    titel: str = Form(...),
    art: str = Form(Leitungsart.WAN.value),
    status: str = Form(AnfrageStatus.ENTWURF.value),
    standort_a_id: str = Form(""),
    standort_b_id: str = Form(""),
    wunsch_technologie: str = Form(""),
    wunsch_down_mbit: str = Form(""),
    wunsch_up_mbit: str = Form(""),
    wunsch_sprachkanaele: str = Form(""),
    wunsch_laufzeit_monate: str = Form(""),
    wunsch_termin: str = Form(""),
    abgabefrist: str = Form(""),
    anforderungen: str = Form(""),
    notizen: str = Form(""),
):
    aid = forms.to_int(anfrage_id)
    anfrage = hole_oder_404(db, Angebotsanfrage, aid) if aid else Angebotsanfrage()

    anfrage.titel = titel.strip()
    anfrage.art = forms.to_enum(Leitungsart, art, Leitungsart.WAN)
    anfrage.status = forms.to_enum(AnfrageStatus, status, AnfrageStatus.ENTWURF)
    anfrage.standort_a_id = forms.to_int(standort_a_id)
    anfrage.standort_b_id = forms.to_int(standort_b_id)
    anfrage.wunsch_technologie = forms.to_enum(Technologie, wunsch_technologie)
    anfrage.wunsch_down_mbit = forms.to_int(wunsch_down_mbit)
    anfrage.wunsch_up_mbit = forms.to_int(wunsch_up_mbit)
    anfrage.wunsch_sprachkanaele = forms.to_int(wunsch_sprachkanaele)
    anfrage.wunsch_laufzeit_monate = forms.to_int(wunsch_laufzeit_monate)
    anfrage.wunsch_termin = forms.to_date(wunsch_termin)
    anfrage.abgabefrist = forms.to_date(abgabefrist)
    anfrage.anforderungen = forms.to_str(anforderungen)
    anfrage.notizen = forms.to_str(notizen)

    db.add(anfrage)
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage.id}", status_code=303)


@router.post("/{anfrage_id}/loeschen")
def loeschen(anfrage_id: int, db: Session = Depends(get_db)):
    db.delete(hole_oder_404(db, Angebotsanfrage, anfrage_id))
    db.commit()
    return RedirectResponse("/anfragen", status_code=303)


@router.post("/{anfrage_id}/provider-hinzufuegen")
def provider_hinzufuegen(
    anfrage_id: int,
    db: Session = Depends(get_db),
    provider_ids: list[int] = Form(default=[]),
):
    anfrage = hole_oder_404(db, Angebotsanfrage, anfrage_id)
    vorhanden = {a.provider_id for a in anfrage.angebote}
    for pid in provider_ids:
        if pid not in vorhanden:
            anfrage.angebote.append(Angebot(provider_id=pid, status=AngebotStatus.ANGEFRAGT))
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.post("/{anfrage_id}/versenden")
def versenden(anfrage_id: int, db: Session = Depends(get_db)):
    from datetime import date

    anfrage = hole_oder_404(db, Angebotsanfrage, anfrage_id)
    if not anfrage.angebote:
        raise HTTPException(status_code=400, detail="Der Anfrage ist kein Provider zugeordnet.")
    for angebot in anfrage.angebote:
        if angebot.angefragt_am is None:
            angebot.angefragt_am = date.today()
    anfrage.status = AnfrageStatus.VERSENDET
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.get("/{anfrage_id}/angebote/{angebot_id}", response_class=HTMLResponse)
def angebot_bearbeiten(
    anfrage_id: int, angebot_id: int, request: Request, db: Session = Depends(get_db)
):
    angebot = hole_oder_404(db, Angebot, angebot_id)
    if angebot.anfrage_id != anfrage_id:
        raise HTTPException(status_code=404, detail="Angebot gehoert nicht zu dieser Anfrage.")
    return templates.TemplateResponse(
        request,
        "anfragen/angebot_formular.html",
        {"angebot": angebot, "anschreiben": anfragetext(angebot.anfrage, angebot)},
    )


@router.post("/{anfrage_id}/angebote/{angebot_id}/speichern")
def angebot_speichern(
    anfrage_id: int,
    angebot_id: int,
    db: Session = Depends(get_db),
    status: str = Form(AngebotStatus.ANGEBOTEN.value),
    angebotsnummer: str = Form(""),
    angefragt_am: str = Form(""),
    eingegangen_am: str = Form(""),
    gueltig_bis: str = Form(""),
    technologie: str = Form(""),
    bandbreite_down_mbit: str = Form(""),
    bandbreite_up_mbit: str = Form(""),
    sprachkanaele: str = Form(""),
    kosten_monatlich: str = Form(""),
    kosten_einmalig: str = Form(""),
    laufzeit_monate: str = Form(""),
    bereitstellung_wochen: str = Form(""),
    sla: str = Form(""),
    dokument_link: str = Form(""),
    notizen: str = Form(""),
):
    angebot = hole_oder_404(db, Angebot, angebot_id)
    if angebot.anfrage_id != anfrage_id:
        raise HTTPException(status_code=404, detail="Angebot gehoert nicht zu dieser Anfrage.")

    angebot.status = forms.to_enum(AngebotStatus, status, AngebotStatus.ANGEBOTEN)
    angebot.angebotsnummer = forms.to_str(angebotsnummer)
    angebot.angefragt_am = forms.to_date(angefragt_am)
    angebot.eingegangen_am = forms.to_date(eingegangen_am)
    angebot.gueltig_bis = forms.to_date(gueltig_bis)
    angebot.technologie = forms.to_enum(Technologie, technologie)
    angebot.bandbreite_down_mbit = forms.to_int(bandbreite_down_mbit)
    angebot.bandbreite_up_mbit = forms.to_int(bandbreite_up_mbit)
    angebot.sprachkanaele = forms.to_int(sprachkanaele)
    angebot.kosten_monatlich = forms.to_decimal(kosten_monatlich)
    angebot.kosten_einmalig = forms.to_decimal(kosten_einmalig)
    angebot.laufzeit_monate = forms.to_int(laufzeit_monate)
    angebot.bereitstellung_wochen = forms.to_int(bereitstellung_wochen)
    angebot.sla = forms.to_str(sla)
    angebot.dokument_link = forms.to_str(dokument_link)
    angebot.notizen = forms.to_str(notizen)

    if (
        angebot.status == AngebotStatus.ANGEBOTEN
        and angebot.anfrage.status == AnfrageStatus.VERSENDET
    ):
        angebot.anfrage.status = AnfrageStatus.ANGEBOTE_ERHALTEN

    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.post("/{anfrage_id}/angebote/{angebot_id}/loeschen")
def angebot_loeschen(anfrage_id: int, angebot_id: int, db: Session = Depends(get_db)):
    angebot = hole_oder_404(db, Angebot, angebot_id)
    if angebot.anfrage_id != anfrage_id:
        raise HTTPException(status_code=404, detail="Angebot gehoert nicht zu dieser Anfrage.")
    db.delete(angebot)
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.post("/{anfrage_id}/angebote/{angebot_id}/beauftragen")
def beauftragen(anfrage_id: int, angebot_id: int, db: Session = Depends(get_db)):
    angebot = hole_oder_404(db, Angebot, angebot_id)
    if angebot.anfrage_id != anfrage_id:
        raise HTTPException(status_code=404, detail="Angebot gehoert nicht zu dieser Anfrage.")
    leitung = angebot_beauftragen(db, angebot)
    return RedirectResponse(f"/leitungen/{leitung.id}/bearbeiten", status_code=303)
