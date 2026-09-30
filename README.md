# WAN- & TK-Leitungstool

Mandantenfaehige Dokumentation von WAN- und TK-Leitungen inklusive Abwicklung von
Angebotsanfragen. Ausgelegt fuer den Betrieb in einer abgeschotteten Behoerdenumgebung:
Docker auf Linux, MySQL, keine externen Aufrufe zur Laufzeit.

Stack: FastAPI, SQLAlchemy, Jinja2, MySQL 8.4.

---

## Mandantentrennung

Jeder Fachdatensatz (Standort, Provider, Leitung, Angebotsanfrage) gehoert genau einem
Mandanten. Mandanten bilden die Organisationsstruktur ab:

| Art | Beispiel |
| --- | --- |
| `Amt` | Amt Musterland |
| `Gemeinde` | Gemeinde Musterhausen |
| `Stadt` | Stadt Musterstadt |
| `Kreis` | Kreis Musterland |
| `Zweckverband` | Zweckverband IT |

Mandanten koennen einander untergeordnet werden (z.B. Gemeinden unter einem Kreis).

**Durchsetzung:** Die Einschraenkung erfolgt serverseitig in jeder Abfrage, nicht in der
Oberflaeche. Zugriffe auf fremde Datensaetze liefern bewusst `404` statt `403`, damit die
Existenz fremder Daten nicht erkennbar wird. Auch Verknuepfungen werden geprueft: eine
Leitung kann keinen Standort eines anderen Mandanten referenzieren.

### Rollen

| Rolle | Rechte |
| --- | --- |
| `Leser` | nur lesen |
| `Bearbeiter` | Fachdaten im eigenen Mandanten pflegen |
| `Mandant-Administrator` | zusaetzlich Konten des eigenen Mandanten, Protokolleinsicht |
| `Administrator` | alle Mandanten, Mandantenverwaltung |

Zusaetzlich gibt es pro Konto die Option **untergeordnete Mandanten sehen**. Ein Kreis-Konto
sieht damit die Leitungen seiner Gemeinden, darf sie aber nicht aendern &ndash; geschrieben
wird ausschliesslich im eigenen Mandanten (Ausnahme: `Administrator`).

---

## Sicherheitsmerkmale

| Bereich | Umsetzung |
| --- | --- |
| Anmeldung | Lokale Konten, Argon2id (`t=3, m=64 MiB, p=4`) |
| Brute-Force | Kontosperre nach 5 Fehlversuchen fuer 15 Minuten, einheitliche Fehlermeldung |
| Sitzung | Signiertes Cookie, `HttpOnly`, `SameSite=Strict`, `Secure`; Leerlauf 20 min, Maximaldauer 8 h |
| Session Fixation | Sitzung wird nach erfolgreicher Anmeldung verworfen und neu aufgebaut |
| Sperrung | Deaktivierte Konten verlieren ihre Sitzung beim naechsten Zugriff, nicht erst beim Ablauf |
| CSRF | Token in jedem schreibenden Formular, Pruefung zentral in der Middleware |
| Passwoerter | Mindestens 12 Zeichen, Gross/Klein, Ziffer, Sonderzeichen; Wechsel beim Erstzugang erzwungen |
| Header | Strikte CSP (`default-src 'none'`), HSTS, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `Cache-Control: no-store` |
| Assets | Bootstrap liegt lokal im Repository, Pruefsumme in `app/static/vendor/SHA256SUMS`; kein CDN, kein Inline-JavaScript |
| Host-Header | `TrustedHostMiddleware`, konfigurierbar ueber `ERLAUBTE_HOSTS` |
| Protokollierung | Revisionsfestes Audit-Log: Anmeldungen, Fehlversuche, Aenderungen, Exporte |
| Container | Nicht-Root (UID 10001), `read_only`, `cap_drop: ALL`, `no-new-privileges`, Healthcheck |
| Geheimnisse | DB-Passwoerter als Docker-Secrets, `.env` nicht im Git |
| API-Doku | Swagger im Produktionsbetrieb abgeschaltet (`DOCS_AKTIV=false`) |

Nicht enthalten und bewusst dem Betrieb ueberlassen: TLS-Terminierung, zentrale
Protokollausleitung (SIEM) und Datensicherung.

> **TLS ist Pflicht.** Die Anwendung bindet sich per Compose nur an `127.0.0.1`. Davor
> gehoert ein Reverse Proxy mit TLS. Ohne TLS greift `COOKIE_SECURE=true` nicht und die
> Anmeldung funktioniert nicht.

---

## Inbetriebnahme (Docker auf Linux)

```bash
git clone https://github.com/BartelLuis/WAN-Tool.git
cd WAN-Tool

# Datenbank-Geheimnisse anlegen
mkdir -p secrets && chmod 700 secrets
openssl rand -base64 24 > secrets/mysql_root_password
openssl rand -base64 24 > secrets/mysql_password
chmod 600 secrets/*

# Konfiguration
cp .env.example .env
chmod 600 .env
# in .env eintragen:
#   MYSQL_PASSWORD  = Inhalt von secrets/mysql_password
#   SESSION_SECRET  = openssl rand -base64 48
#   ADMIN_PASSWORT  = Erstpasswort des Administrators
#   BEHOERDE, ERLAUBTE_HOSTS, START_MANDANT_*

docker compose up -d --build
```

Oberflaeche: `http://127.0.0.1:8000` (hinter dem Reverse Proxy die dienstliche URL).

Beim ersten Start entstehen der in `.env` beschriebene Mandant und das
Administratorkonto. Das Passwort muss bei der ersten Anmeldung geaendert werden.
`ADMIN_PASSWORT` danach aus der `.env` entfernen &ndash; es wird nur einmalig ausgewertet.

### Ersteinrichtung in der Oberflaeche

1. Anmelden, Passwort aendern.
2. **Mandanten** anlegen (Aemter, Gemeinden, Staedte; bei Bedarf einem Kreis unterstellen).
3. **Benutzer** anlegen. Das Startpasswort wird genau einmal angezeigt.
4. Je Mandant Standorte und Provider pflegen, danach Leitungen und Angebotsanfragen.

---

## Angebotsanfrage

1. Bedarf erfassen (Standorte, Technologie, Bandbreite, Laufzeit, Abgabefrist).
2. Provider des Mandanten zuordnen.
3. Generiertes Anschreiben kopieren und versenden, Anfrage als versendet markieren.
4. Eingehende Angebote je Provider erfassen.
5. Vergleich ueber die Gesamtkosten der Laufzeit; das guenstigste Angebot wird markiert.
6. **Beauftragen** setzt die uebrigen Angebote auf abgelehnt und legt die dokumentierte
   Leitung im selben Mandanten an.

---

## Entwicklung und Tests

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt

pytest                       # gegen SQLite
ruff check . && ruff format --check .
bandit -r app -ll
```

Gegen MySQL testen:

```bash
export TEST_DATABASE_URL='mysql+pymysql://wantool:test@127.0.0.1:3306/wantool?charset=utf8mb4'
pytest
```

Anwendung ohne Container starten (nur fuer Entwicklung):

```bash
export UMGEBUNG=entwicklung COOKIE_SECURE=false DOCS_AKTIV=true
export SESSION_SECRET="$(openssl rand -base64 48)"
export DATABASE_URL_OVERRIDE="sqlite:///./entwicklung.db"
uvicorn app.main:app --reload
```

Ohne gesetztes `ADMIN_PASSWORT` erzeugt die Anwendung ausserhalb des Produktionsbetriebs
ein zufaelliges Erstpasswort und schreibt es ins Log.

### Fremd-Assets aktualisieren

```bash
tools/hole-assets.sh        # laedt Bootstrap und prueft die Pruefsumme
```

### Werkzeuge

| Skript | Zweck |
| --- | --- |
| `tools/hole-assets.sh` / `.ps1` | Bootstrap laden und Pruefsumme schreiben |
| `tools/testkonfiguration.ps1` | lokale `.env` und `secrets/` mit Zufallswerten erzeugen |
| `tools/abnahme.ps1` | Abnahmetest gegen einen laufenden Stack (Header, Login, Mandantentrennung, Sperre) |

---

## CI

`.github/workflows/ci.yml`:

| Job | Inhalt |
| --- | --- |
| `lint` | `ruff check`, `ruff format --check` |
| `test` | pytest gegen SQLite **und** MySQL 8.4 (Service-Container) |
| `sicherheit` | `bandit`, `pip-audit` |
| `container` | Hadolint, Pruefsummen der Assets, Image-Build, Nicht-Root-Nachweis, Trivy (HIGH/CRITICAL brechen ab) |
| `integration` | `docker compose up` auf Linux, prueft Health, Login, Security-Header und Anmeldezwang |

`.github/workflows/codeql.yml` ergaenzt die statische Analyse, `dependabot.yml` haelt
Python-, Docker- und Action-Abhaengigkeiten aktuell.

---

## Projektstruktur

| Pfad | Inhalt |
| --- | --- |
| `app/models.py` | Mandant, Benutzer, Audit-Log, Standort, Provider, Leitung, Anfrage, Angebot |
| `app/deps.py` | Rollenpruefung und Mandantenfilter fuer jede Abfrage |
| `app/middleware.py` | Sicherheits-Header, Sitzungspruefung, CSRF |
| `app/security.py` | Argon2, Passwortregeln, Audit-Protokoll |
| `app/routers/` | Anmeldung, Fachmodule, Verwaltung, REST-API |
| `app/services.py` | Anschreiben, Beauftragung, CSV-Export |
| `app/templates/` | Oberflaeche (ohne Inline-JavaScript) |
| `tests/` | Sicherheits-, Rollen- und Mandantentests |

---

## Betriebshinweise

- Sicherung: Volume `db_data` bzw. `mysqldump`; das Audit-Log ist Teil der Datenbank.
- Das Audit-Log ist ueber die Oberflaeche nur lesbar und wird nicht automatisch geloescht;
  Aufbewahrungsfristen sind organisatorisch festzulegen.
- `docker compose down -v` loescht alle Daten einschliesslich des Protokolls.
- `SESSION_SECRET` ist der Schluessel aller Sitzungscookies; eine Aenderung meldet alle
  Benutzer ab.
- Setze `VERTRAUE_PROXY_HEADER=true` nur, wenn ein vertrauenswuerdiger Reverse Proxy
  `X-Forwarded-For` setzt &ndash; sonst sind die protokollierten IP-Adressen faelschbar.
