from datetime import date

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
    hole_im_mandanten,
)
from app.models import (
    AnfrageStatus,
    Angebot,
    Angebotsanfrage,
    AngebotStatus,
    Leitungsart,
    Provider,
    Standort,
    Technologie,
)
from app.security import protokolliere
from app.services import anfragetext, angebot_beauftragen
from app.templating import templates

router = APIRouter(prefix="/anfragen", tags=["Angebotsanfragen"])


def _auswahllisten(db: Session, benutzer: Angemeldet) -> dict:
    standorte = db.scalars(
        beschraenke(select(Standort).order_by(Standort.name), Standort, db, benutzer)
    )
    return {
        "standorte": list(standorte),
        "mandanten": auswahl_mandanten(db, benutzer),
    }


def _angebot_holen(db: Session, anfrage_id: int, angebot_id: int, benutzer: Angemeldet) -> Angebot:
    angebot = db.get(Angebot, angebot_id)
    if angebot is None or angebot.anfrage_id != anfrage_id:
        raise HTTPException(status_code=404, detail="Angebot nicht gefunden.")
    hole_bearbeitbar(db, Angebotsanfrage, anfrage_id, benutzer)
    return angebot


@router.get("", response_class=HTMLResponse)
def liste(
    request: Request,
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
    status: str = "",
):
    stmt = beschraenke(
        select(Angebotsanfrage).order_by(Angebotsanfrage.id.desc()),
        Angebotsanfrage,
        db,
        benutzer,
    )
    if status_enum := forms.to_enum(AnfrageStatus, status):
        stmt = stmt.where(Angebotsanfrage.status == status_enum)
    return templates.TemplateResponse(
        request,
        "anfragen/liste.html",
        {"anfragen": list(db.scalars(stmt)), "filter": {"status": status}},
    )


@router.get("/neu", response_class=HTMLResponse)
def neu(request: Request, bearbeiter: Bearbeiter, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "anfragen/formular.html", {"anfrage": None, **_auswahllisten(db, bearbeiter)}
    )


@router.get("/{anfrage_id}", response_class=HTMLResponse)
def detail(
    anfrage_id: int,
    request: Request,
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
):
    anfrage = hole_im_mandanten(db, Angebotsanfrage, anfrage_id, benutzer)
    vergeben = {a.provider_id for a in anfrage.angebote}
    offene_provider = [
        p
        for p in db.scalars(
            select(Provider)
            .where(Provider.mandant_id == anfrage.mandant_id)
            .order_by(Provider.name)
        )
        if p.id not in vergeben
    ]
    bestes = min(
        (a for a in anfrage.angebote if a.tco is not None), key=lambda a: a.tco, default=None
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
def bearbeiten(
    anfrage_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    anfrage = hole_bearbeitbar(db, Angebotsanfrage, anfrage_id, bearbeiter)
    return templates.TemplateResponse(
        request, "anfragen/formular.html", {"anfrage": anfrage, **_auswahllisten(db, bearbeiter)}
    )


@router.post("/speichern")
def speichern(
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
    anfrage_id: str = Form(""),
    mandant_id: str = Form(...),
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
    ziel_mandant = forms.to_int(mandant_id)
    if ziel_mandant is None or not darf_bearbeiten(db, bearbeiter, ziel_mandant):
        raise HTTPException(status_code=403, detail="Unzulaessiger Mandant.")

    for standort_id in (forms.to_int(standort_a_id), forms.to_int(standort_b_id)):
        if standort_id is None:
            continue
        standort = hole_im_mandanten(db, Standort, standort_id, bearbeiter)
        if standort.mandant_id != ziel_mandant:
            raise HTTPException(
                status_code=400, detail="Standorte muessen zum gewaehlten Mandanten gehoeren."
            )

    aid = forms.to_int(anfrage_id)
    anfrage = hole_bearbeitbar(db, Angebotsanfrage, aid, bearbeiter) if aid else Angebotsanfrage()

    anfrage.mandant_id = ziel_mandant
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
    db.flush()
    protokolliere(
        db,
        request,
        bearbeiter,
        "gespeichert",
        "Angebotsanfrage",
        anfrage.id,
        anfrage.titel,
        mandant_id=ziel_mandant,
    )
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage.id}", status_code=303)


@router.post("/{anfrage_id}/loeschen")
def loeschen(
    anfrage_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    anfrage = hole_bearbeitbar(db, Angebotsanfrage, anfrage_id, bearbeiter)
    protokolliere(
        db,
        request,
        bearbeiter,
        "geloescht",
        "Angebotsanfrage",
        anfrage.id,
        anfrage.titel,
        mandant_id=anfrage.mandant_id,
    )
    db.delete(anfrage)
    db.commit()
    return RedirectResponse("/anfragen", status_code=303)


@router.post("/{anfrage_id}/provider-hinzufuegen")
def provider_hinzufuegen(
    anfrage_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
    provider_ids: list[int] = Form(default=[]),
):
    anfrage = hole_bearbeitbar(db, Angebotsanfrage, anfrage_id, bearbeiter)
    vorhanden = {a.provider_id for a in anfrage.angebote}
    for pid in provider_ids:
        provider = hole_im_mandanten(db, Provider, pid, bearbeiter)
        if provider.mandant_id != anfrage.mandant_id:
            raise HTTPException(
                status_code=400, detail="Provider gehoert zu einem anderen Mandanten."
            )
        if pid not in vorhanden:
            anfrage.angebote.append(Angebot(provider_id=pid, status=AngebotStatus.ANGEFRAGT))
    protokolliere(
        db,
        request,
        bearbeiter,
        "provider_zugeordnet",
        "Angebotsanfrage",
        anfrage.id,
        f"{len(provider_ids)} Provider",
        mandant_id=anfrage.mandant_id,
    )
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.post("/{anfrage_id}/versenden")
def versenden(
    anfrage_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    anfrage = hole_bearbeitbar(db, Angebotsanfrage, anfrage_id, bearbeiter)
    if not anfrage.angebote:
        raise HTTPException(status_code=400, detail="Der Anfrage ist kein Provider zugeordnet.")
    for angebot in anfrage.angebote:
        if angebot.angefragt_am is None:
            angebot.angefragt_am = date.today()
    anfrage.status = AnfrageStatus.VERSENDET
    protokolliere(
        db,
        request,
        bearbeiter,
        "anfrage_versendet",
        "Angebotsanfrage",
        anfrage.id,
        anfrage.titel,
        mandant_id=anfrage.mandant_id,
    )
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.get("/{anfrage_id}/angebote/{angebot_id}", response_class=HTMLResponse)
def angebot_bearbeiten(
    anfrage_id: int,
    angebot_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    angebot = _angebot_holen(db, anfrage_id, angebot_id, bearbeiter)
    return templates.TemplateResponse(
        request,
        "anfragen/angebot_formular.html",
        {"angebot": angebot, "anschreiben": anfragetext(angebot.anfrage, angebot)},
    )


@router.post("/{anfrage_id}/angebote/{angebot_id}/speichern")
def angebot_speichern(
    anfrage_id: int,
    angebot_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
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
    angebot = _angebot_holen(db, anfrage_id, angebot_id, bearbeiter)

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

    protokolliere(
        db,
        request,
        bearbeiter,
        "angebot_erfasst",
        "Angebot",
        angebot.id,
        f"{angebot.provider.name}: {angebot.status.value}",
        mandant_id=angebot.anfrage.mandant_id,
    )
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.post("/{anfrage_id}/angebote/{angebot_id}/loeschen")
def angebot_loeschen(
    anfrage_id: int,
    angebot_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    angebot = _angebot_holen(db, anfrage_id, angebot_id, bearbeiter)
    protokolliere(
        db,
        request,
        bearbeiter,
        "angebot_entfernt",
        "Angebot",
        angebot.id,
        angebot.provider.name,
        mandant_id=angebot.anfrage.mandant_id,
    )
    db.delete(angebot)
    db.commit()
    return RedirectResponse(f"/anfragen/{anfrage_id}", status_code=303)


@router.post("/{anfrage_id}/angebote/{angebot_id}/beauftragen")
def beauftragen(
    anfrage_id: int,
    angebot_id: int,
    request: Request,
    bearbeiter: Bearbeiter,
    db: Session = Depends(get_db),
):
    angebot = _angebot_holen(db, anfrage_id, angebot_id, bearbeiter)
    leitung = angebot_beauftragen(db, angebot)
    protokolliere(
        db,
        request,
        bearbeiter,
        "angebot_beauftragt",
        "Angebot",
        angebot.id,
        f"{angebot.provider.name} -> Leitung #{leitung.id}",
        mandant_id=leitung.mandant_id,
    )
    db.commit()
    return RedirectResponse(f"/leitungen/{leitung.id}/bearbeiten", status_code=303)
