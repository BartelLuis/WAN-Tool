from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms, schemas
from app.database import get_db
from app.deps import Angemeldet, beschraenke, hole_im_mandanten, sichtbare_mandanten
from app.models import (
    Angebotsanfrage,
    Leitung,
    Leitungsart,
    LeitungStatus,
    Mandant,
    Provider,
    Standort,
)

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/mandanten", response_model=list[schemas.MandantOut])
def mandanten(benutzer: Angemeldet, db: Session = Depends(get_db)):
    stmt = select(Mandant).order_by(Mandant.name)
    if (ids := sichtbare_mandanten(db, benutzer)) is not None:
        stmt = stmt.where(Mandant.id.in_(ids))
    return list(db.scalars(stmt))


@router.get("/standorte", response_model=list[schemas.StandortOut])
def standorte(benutzer: Angemeldet, db: Session = Depends(get_db)):
    stmt = beschraenke(select(Standort).order_by(Standort.name), Standort, db, benutzer)
    return list(db.scalars(stmt))


@router.get("/provider", response_model=list[schemas.ProviderOut])
def provider(benutzer: Angemeldet, db: Session = Depends(get_db)):
    stmt = beschraenke(select(Provider).order_by(Provider.name), Provider, db, benutzer)
    return list(db.scalars(stmt))


@router.get("/leitungen", response_model=list[schemas.LeitungOut])
def leitungen(
    benutzer: Angemeldet,
    db: Session = Depends(get_db),
    art: str = "",
    status: str = "",
):
    stmt = beschraenke(select(Leitung).order_by(Leitung.bezeichnung), Leitung, db, benutzer)
    if art_enum := forms.to_enum(Leitungsart, art):
        stmt = stmt.where(Leitung.art == art_enum)
    if status_enum := forms.to_enum(LeitungStatus, status):
        stmt = stmt.where(Leitung.status == status_enum)
    return list(db.scalars(stmt))


@router.get("/leitungen/{leitung_id}", response_model=schemas.LeitungOut)
def leitung(leitung_id: int, benutzer: Angemeldet, db: Session = Depends(get_db)):
    return hole_im_mandanten(db, Leitung, leitung_id, benutzer)


@router.get("/anfragen", response_model=list[schemas.AnfrageOut])
def anfragen(benutzer: Angemeldet, db: Session = Depends(get_db)):
    stmt = beschraenke(
        select(Angebotsanfrage).order_by(Angebotsanfrage.id.desc()),
        Angebotsanfrage,
        db,
        benutzer,
    )
    return list(db.scalars(stmt))


@router.get("/anfragen/{anfrage_id}", response_model=schemas.AnfrageOut)
def anfrage(anfrage_id: int, benutzer: Angemeldet, db: Session = Depends(get_db)):
    return hole_im_mandanten(db, Angebotsanfrage, anfrage_id, benutzer)
