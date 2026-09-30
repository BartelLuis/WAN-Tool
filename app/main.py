import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.deps import Angemeldet, beschraenke, sichtbare_mandanten
from app.middleware import AuthentifizierungsMiddleware, SicherheitsHeaderMiddleware
from app.models import (
    AnfrageStatus,
    Angebotsanfrage,
    Benutzer,
    Leitung,
    LeitungStatus,
    Mandant,
    MandantArt,
    Provider,
    Rolle,
    Standort,
)
from app.routers import anfragen, api, auth, leitungen, provider, standorte, verwaltung
from app.security import hash_passwort
from app.templating import templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("wantool")


def init_db(versuche: int = 30, pause: float = 2.0) -> None:
    for versuch in range(1, versuche + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError as exc:
            logger.warning("Datenbank nicht erreichbar (%s/%s): %s", versuch, versuche, exc)
            time.sleep(pause)
    raise RuntimeError("Datenbankverbindung konnte nicht aufgebaut werden.")


def ersteinrichtung() -> None:
    """Legt beim allerersten Start einen Mandanten und ein Administratorkonto an."""
    db = SessionLocal()
    try:
        if db.scalar(select(func.count(Benutzer.id))):
            return

        mandant = Mandant(
            name=settings.start_mandant_name,
            kennzeichen=settings.start_mandant_kennzeichen.upper(),
            art=MandantArt(settings.start_mandant_art)
            if settings.start_mandant_art in {a.value for a in MandantArt}
            else MandantArt.SONSTIGE,
        )
        db.add(mandant)
        db.flush()

        passwort = settings.admin_passwort
        if not passwort:
            if settings.ist_produktion:
                raise RuntimeError("ADMIN_PASSWORT ist nicht gesetzt. Ersteinrichtung abgebrochen.")
            passwort = secrets.token_urlsafe(16)
            logger.warning("Einmaliges Administratorpasswort: %s", passwort)

        db.add(
            Benutzer(
                benutzername=settings.admin_benutzer.strip().lower(),
                name="Administrator",
                passwort_hash=hash_passwort(passwort),
                rolle=Rolle.ADMIN,
                mandant_id=mandant.id,
                sieht_untergeordnete=True,
                passwort_aendern=True,
            )
        )
        db.commit()
        logger.info(
            "Ersteinrichtung abgeschlossen: Mandant '%s', Administrator '%s'.",
            mandant.name,
            settings.admin_benutzer,
        )
    finally:
        db.close()


def _konfiguration_pruefen() -> None:
    if not settings.ist_produktion:
        return
    if not settings.session_secret or len(settings.session_secret) < 32:
        raise RuntimeError("SESSION_SECRET fehlt oder ist zu kurz (mindestens 32 Zeichen).")
    if not settings.mysql_password:
        raise RuntimeError("MYSQL_PASSWORD ist im Produktionsbetrieb erforderlich.")
    if settings.docs_aktiv:
        logger.warning("Die API-Dokumentation ist im Produktionsbetrieb aktiviert.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _konfiguration_pruefen()
    init_db()
    ersteinrichtung()
    yield


app = FastAPI(
    title=settings.app_title,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_aktiv else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_aktiv else None,
)

# Reihenfolge: zuletzt hinzugefuegte Middleware laeuft zuerst.
app.add_middleware(AuthentifizierungsMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie=settings.session_cookie,
    https_only=settings.cookie_secure,
    same_site="strict",
    max_age=settings.session_maximal_minuten * 60,
)
app.add_middleware(SicherheitsHeaderMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.erlaubte_hosts)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)

app.include_router(auth.router)
app.include_router(standorte.router)
app.include_router(provider.router)
app.include_router(leitungen.router)
app.include_router(anfragen.router)
app.include_router(verwaltung.router)
app.include_router(api.router)


@app.exception_handler(IntegrityError)
def integritaetsfehler(request: Request, exc: IntegrityError):
    meldung = (
        "Ein Datensatz mit diesem Namen existiert in diesem Mandanten bereits."
        if "Duplicate entry" in str(exc.orig) or "UNIQUE constraint" in str(exc.orig)
        else "Die Daten konnten nicht gespeichert werden."
    )
    logger.warning("Integritaetsfehler bei %s: %s", request.url.path, exc.orig)
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=409, content={"detail": meldung})
    return templates.TemplateResponse(
        request, "fehler.html", {"meldung": meldung, "details": None}, status_code=409
    )


@app.exception_handler(HTTPException)
def http_fehler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api") or exc.status_code == 401:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return templates.TemplateResponse(
        request,
        "fehler.html",
        {"meldung": exc.detail, "details": None},
        status_code=exc.status_code,
    )


@app.get("/health", response_class=PlainTextResponse, include_in_schema=False)
def health():
    return "ok"


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, benutzer: Angemeldet, db: Session = Depends(get_db)):
    stichtag = date.today() + timedelta(days=120)

    def zaehle(modell) -> int:
        stmt = beschraenke(select(func.count(modell.id)), modell, db, benutzer)
        return db.scalar(stmt) or 0

    aktiv_stmt = beschraenke(
        select(func.count(Leitung.id)).where(Leitung.status == LeitungStatus.AKTIV),
        Leitung,
        db,
        benutzer,
    )
    kosten_stmt = beschraenke(
        select(func.coalesce(func.sum(Leitung.kosten_monatlich), 0)).where(
            Leitung.status == LeitungStatus.AKTIV
        ),
        Leitung,
        db,
        benutzer,
    )
    offen_stmt = beschraenke(
        select(func.count(Angebotsanfrage.id)).where(
            Angebotsanfrage.status.notin_([AnfrageStatus.BEAUFTRAGT, AnfrageStatus.ABGEBROCHEN])
        ),
        Angebotsanfrage,
        db,
        benutzer,
    )

    kennzahlen = {
        "standorte": zaehle(Standort),
        "provider": zaehle(Provider),
        "leitungen": zaehle(Leitung),
        "aktiv": db.scalar(aktiv_stmt) or 0,
        "kosten": db.scalar(kosten_stmt),
        "offene_anfragen": db.scalar(offen_stmt) or 0,
    }

    auslaufend = db.scalars(
        beschraenke(
            select(Leitung)
            .where(Leitung.vertragsende.is_not(None), Leitung.vertragsende <= stichtag)
            .order_by(Leitung.vertragsende),
            Leitung,
            db,
            benutzer,
        )
    ).all()
    letzte_anfragen = db.scalars(
        beschraenke(
            select(Angebotsanfrage).order_by(Angebotsanfrage.id.desc()).limit(5),
            Angebotsanfrage,
            db,
            benutzer,
        )
    ).all()
    nach_status = db.execute(
        beschraenke(
            select(Leitung.status, func.count(Leitung.id)).group_by(Leitung.status),
            Leitung,
            db,
            benutzer,
        )
    ).all()

    ids = sichtbare_mandanten(db, benutzer)
    mandanten_stmt = select(Mandant).order_by(Mandant.name)
    if ids is not None:
        mandanten_stmt = mandanten_stmt.where(Mandant.id.in_(ids))

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "kennzahlen": kennzahlen,
            "auslaufend": auslaufend,
            "letzte_anfragen": letzte_anfragen,
            "nach_status": nach_status,
            "mandanten": list(db.scalars(mandanten_stmt)),
        },
    )
