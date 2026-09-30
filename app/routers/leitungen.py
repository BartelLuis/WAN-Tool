from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import or_, select
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
    hole_im_mandanten,
)
from app.models import (
    Leitung,
    Leitungsart,
    LeitungStatus,
    Provider,
    Standort,
    Technologie,
)
from app.security import protokolliere
from app.services import leitungen_csv
from app.templating import templates

router = APIRouter(prefix="/leitungen", tags=["Leitungen"])


def _auswahllisten(db: Session, benutzer: Angemeldet) -> dict:
    """Standorte und Provider, die dem Benutzer sichtbar sind."""
    standorte = db.scalars(
        beschraenke(select(Standort).order_by(Standort.name), Standort, db, benutzer)
    )
    providerliste = db.scalars(
        beschraenke(select(Provider).order_by(Provider.name), Provider, db, benutzer)
    )
    return {
        "standorte": list(standorte),
        "providerliste": list(providerliste),
        "mandanten": auswahl_mandanten(db, benutzer),
    }


def _gefiltert(
    db: Session,
    benutzer: Angemeldet,
    art: str,
    status: str,
    provider_id: str,
    suche: str,
) -> list[Leitung]:
    stmt = beschraenke(select(Leitung).order_by(Leitung.bezeichnung), Leitung, db, benutzer)
    if art_enum := forms.to_enum(Leitungsart, art):
        stmt = stmt.where(Leitung.art == art_enum)
    if status_enum := forms.to_enum(LeitungStatus, status):
        stmt = stmt.where(Leitung.status == status_enum)
    if pid := forms.to_int(provider_id):
        stmt = stmt.where(Leitung.provider_id == pid)
    if begriff := forms.to_str(suche):
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
    return list(db.scalars(stmt))


@router.get("", response_class=HTMLResponse)
def liste(
    request: Request,
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
    art: str = "",
    status: str = "",
    provider_id: str = "",
    suche: str = "",
):
    return templates.TemplateResponse(
        request,
        "leitungen/liste.html",
        {
            "leitungen": _gefiltert(db, benutzer, art, status, provider_id, suche),
            "filter": {"art": art, "status": status, "provider_id": provider_id, "suche": suche},
            **_auswahllisten(db, benutzer),
        },
    )


@router.get("/export.csv")
def export(
    request: Request,
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
    art: str = "",
    status: str = "",
    provider_id: str = "",
    suche: str = "",
):
    leitungen = _gefiltert(db, benutzer, art, status, provider_id, suche)
    protokolliere(db, request, benutzer, "export", "Leitung", None, f"{len(leitungen)} Datensaetze")
    db.commit()
    return Response(
        # BOM, damit Excel die Umlaute korrekt erkennt
        content=("\ufeff" + leitungen_csv(leitungen)).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leitungen.csv"'},
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request, bearbeiter: Bearbeiter, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "leitungen/formular.html", {"leitung": None, **_auswahllisten(db, bearbeiter)}
    )


@router.get("/{leitung_id}", response_class=HTMLResponse)
def detail(
    leitung_id: int,
    request: Request,
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
):
    leitung = hole_im_mandanten(db, Leitung, leitung_id, benutzer)
    return templates.TemplateResponse(request, "leitungen/detail.html", {"leitung": leitung})


@router.get("/{leitung_id}/bearbeiten", response_class=HTMLResponse)
def bearbeiten(
    leitung_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    leitung = hole_bearbeitbar(db, Leitung, leitung_id, bearbeiter)
    return templates.TemplateResponse(
        request, "leitungen/formular.html", {"leitung": leitung, **_auswahllisten(db, bearbeiter)}
    )


def _pruefe_zuordnung(
    db: Session,
    benutzer: Angemeldet,
    mandant_id: int,
    standort_a: int | None,
    standort_b: int | None,
    provider: int | None,
) -> None:
    """Verhindert, dass Standorte oder Provider fremder Mandanten verknuepft werden."""
    zu_pruefen = ((Standort, standort_a), (Standort, standort_b), (Provider, provider))
    for modell, obj_id in zu_pruefen:
        if obj_id is None:
            continue
        obj = hole_im_mandanten(db, modell, obj_id, benutzer)
        if obj.mandant_id != mandant_id:
            raise HTTPException(
                status_code=400,
                detail="Standorte und Provider muessen zum gewaehlten Mandanten gehoeren.",
            )


@router.post("/speichern")
def speichern(
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
    leitung_id: str = Form(""),
    mandant_id: str = Form(...),
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
    ziel_mandant = forms.to_int(mandant_id)
    if ziel_mandant is None or not darf_bearbeiten(db, bearbeiter, ziel_mandant):
        raise HTTPException(status_code=403, detail="Unzulaessiger Mandant.")

    a_id, b_id, p_id = (
        forms.to_int(standort_a_id),
        forms.to_int(standort_b_id),
        forms.to_int(provider_id),
    )
    _pruefe_zuordnung(db, bearbeiter, ziel_mandant, a_id, b_id, p_id)

    lid = forms.to_int(leitung_id)
    leitung = hole_bearbeitbar(db, Leitung, lid, bearbeiter) if lid else Leitung()

    leitung.mandant_id = ziel_mandant
    leitung.bezeichnung = bezeichnung.strip()
    leitung.art = forms.to_enum(Leitungsart, art, Leitungsart.WAN)
    leitung.technologie = forms.to_enum(Technologie, technologie, Technologie.SONSTIGE)
    leitung.status = forms.to_enum(LeitungStatus, status, LeitungStatus.GEPLANT)
    leitung.provider_id = p_id
    leitung.standort_a_id = a_id
    leitung.standort_b_id = b_id
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
    db.flush()
    protokolliere(
        db,
        request,
        bearbeiter,
        "gespeichert",
        "Leitung",
        leitung.id,
        leitung.bezeichnung,
        mandant_id=ziel_mandant,
    )
    db.commit()
    return RedirectResponse(f"/leitungen/{leitung.id}", status_code=303)


@router.post("/{leitung_id}/loeschen")
def loeschen(
    leitung_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    leitung = hole_bearbeitbar(db, Leitung, leitung_id, bearbeiter)
    protokolliere(
        db,
        request,
        bearbeiter,
        "geloescht",
        "Leitung",
        leitung.id,
        leitung.bezeichnung,
        mandant_id=leitung.mandant_id,
    )
    db.delete(leitung)
    db.commit()
    return RedirectResponse("/leitungen", status_code=303)
