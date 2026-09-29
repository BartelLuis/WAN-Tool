# WAN- & TK-Leitungstool

Dokumentation von WAN- und TK-Leitungen inklusive Abwicklung von Angebotsanfragen.
Stack: FastAPI + SQLAlchemy + Jinja2/Bootstrap, MySQL 8 im Docker-Container.

## Funktionsumfang

- **Standorte** und **Provider** als Stammdaten
- **Leitungen**: WAN und TK, mit Technik (Bandbreite, Circuit-ID, Transfernetz, Sprachkanaele,
  Rufnummernblock, SLA) und Vertragsdaten (Kosten, Laufzeit, Kuendigungsfrist)
- Filter, Volltextsuche und CSV-Export der Leitungsliste
- **Angebotsanfragen**: Bedarf erfassen, Provider zuordnen, versandfertiges Anschreiben
  generieren, Angebote je Provider erfassen und über Gesamtkosten (TCO) vergleichen
- Beauftragung eines Angebots legt automatisch die dokumentierte Leitung an
- Dashboard mit Kennzahlen und Warnung vor auslaufenden Vertraegen
- Lesende REST-API unter `/api`, interaktive Doku unter `/docs`

## Start

```powershell
Copy-Item .env.example .env
# Passwoerter in .env anpassen
docker compose up -d --build
```

Oberflaeche: http://localhost:8000 — API-Doku: http://localhost:8000/docs

Die Tabellen werden beim ersten Start automatisch angelegt.

## Lokale Entwicklung (App ausserhalb von Docker)

```powershell
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Die App liest die Zugangsdaten aus `.env`; im lokalen Betrieb greift sie über den
gemappten Port `127.0.0.1:3307` auf die Datenbank zu.

## Projektstruktur

| Pfad | Inhalt |
| --- | --- |
| `app/models.py` | Datenmodell (Standort, Provider, Leitung, Angebotsanfrage, Angebot) |
| `app/routers/` | Web- und API-Routen |
| `app/services.py` | Anschreiben-Generierung, Beauftragung, CSV-Export |
| `app/templates/` | Jinja2-Oberflaeche |

## Hinweise

- Das Tool enthaelt keine Benutzerverwaltung. Betreibe es nur im internen Netz
  oder stelle einen Reverse Proxy mit Authentifizierung davor.
- Der MySQL-Port ist standardmaessig nur an `127.0.0.1` gebunden.
- Daten liegen im Docker-Volume `db_data` und ueberleben `docker compose down`
  (nicht jedoch `docker compose down -v`).
