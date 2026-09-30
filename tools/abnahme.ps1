# Abnahmetest gegen einen laufenden Stack. Nutzt curl, um PowerShell-Eigenheiten
# bei Fehlerantworten zu umgehen.
$ErrorActionPreference = 'Stop'
$b = 'http://127.0.0.1:8000'
$jar = Join-Path $env:TEMP 'wantool-cookies.txt'
Remove-Item $jar -ErrorAction SilentlyContinue

function Token {
    # -L folgt der Umleitung, wenn bereits eine Sitzung besteht.
    $html = (curl.exe -s -L -c $jar -b $jar "$b/login") -join "`n"
    if ($html -match 'name="csrf_token" value="([^"]+)"') { return $Matches[1] }
    throw 'Kein CSRF-Token gefunden'
}
function Anmelden($nutzer, $pass) {
    $t = Token
    curl.exe -s -c $jar -b $jar -o NUL -w '%{http_code}' -X POST "$b/login" `
        --data-urlencode "benutzername=$nutzer" --data-urlencode "passwort=$pass" `
        --data-urlencode "csrf_token=$t"
}
function Code($pfad) { curl.exe -s -c $jar -b $jar -o NUL -w '%{http_code}' "$b$pfad" }
function Senden($pfad, [string[]]$felder) {
    $t = Token
    $argumente = @('-s', '-c', $jar, '-b', $jar, '-o', 'NUL', '-w', '%{http_code}', '-X', 'POST', "$b$pfad")
    foreach ($f in $felder) { $argumente += @('--data-urlencode', $f) }
    $argumente += @('--data-urlencode', "csrf_token=$t")
    & curl.exe @argumente
}

$adminPass = ((Get-Content .env | Select-String '^ADMIN_PASSWORT=') -split '=', 2)[1]

Write-Host "`n=== Sicherheits-Kopfzeilen ==="
$kopf = (curl.exe -sI "$b/login") -join "`n"
foreach ($h in 'content-security-policy', 'x-frame-options', 'x-content-type-options',
    'referrer-policy', 'cache-control', 'permissions-policy') {
    ($kopf -split "`n" | Select-String "^$h" | Select-Object -First 1).ToString().Trim()
}
"Kein CDN im HTML     : " + (-not (((curl.exe -s "$b/login") -join '') -match 'cdn\.'))

Write-Host "`n=== Zugriffsschutz ohne Anmeldung ==="
"/leitungen  -> " + (Code '/leitungen') + " (erwartet 303)"
"/api/...    -> " + (Code '/api/leitungen') + " (erwartet 401)"
"/health     -> " + (Code '/health') + " (erwartet 200)"
"/docs       -> " + (Code '/docs') + " (erwartet 303, Doku abgeschaltet)"
"POST ohne CSRF-Token -> " + (curl.exe -s -o NUL -w '%{http_code}' -X POST "$b/login" -d 'benutzername=admin&passwort=x') + " (erwartet 403)"

Write-Host "`n=== Anmeldung und erzwungener Passwortwechsel ==="
"Anmeldung           -> " + (Anmelden 'admin' $adminPass) + " (erwartet 303)"
"Dashboard vor Wechsel -> " + (Code '/') + " (erwartet 303 nach /passwort)"
$neu = 'Behoerde!Test2026'
"Passwortwechsel     -> " + (Senden '/passwort' @("altes_passwort=$adminPass", "neues_passwort=$neu", "wiederholung=$neu")) + " (erwartet 303)"
"Dashboard danach    -> " + (Code '/') + " (erwartet 200)"
"Schwaches Passwort  -> " + (Senden '/passwort' @("altes_passwort=$neu", 'neues_passwort=kurz', 'wiederholung=kurz')) + " (erwartet 400)"

Write-Host "`n=== Mandanten ==="
foreach ($m in @(
    @{ n = 'Musterhausen'; k = 'GEM-MH'; a = 'Gemeinde' },
    @{ n = 'Musterstadt'; k = 'ST-MS'; a = 'Stadt' },
    @{ n = 'Bauamt Musterland'; k = 'AMT-BA'; a = 'Amt' })) {
    "{0,-20} -> {1}" -f $m.n, (Senden '/verwaltung/mandanten/speichern' @("name=$($m.n)", "kennzeichen=$($m.k)", "art=$($m.a)", 'aktiv=1'))
}
$mandanten = (curl.exe -s -b $jar -c $jar "$b/api/mandanten") | ConvertFrom-Json
$mandanten | ForEach-Object { "  #{0} {1} {2} [{3}]" -f $_.id, $_.art, $_.name, $_.kennzeichen }
$kreis = $mandanten | Where-Object { $_.art -eq 'Kreis' }
$gemeinde = $mandanten | Where-Object { $_.kennzeichen -eq 'GEM-MH' }
$stadt = $mandanten | Where-Object { $_.kennzeichen -eq 'ST-MS' }
"Gemeinde dem Kreis unterstellen -> " + (Senden '/verwaltung/mandanten/speichern' @(
    "mandant_id=$($gemeinde.id)", 'name=Musterhausen', 'kennzeichen=GEM-MH',
    'art=Gemeinde', "uebergeordnet_id=$($kreis.id)", 'aktiv=1'))

Write-Host "`n=== Fachdaten je Mandant ==="
foreach ($m in @($gemeinde, $stadt)) {
    Senden '/standorte/speichern' @("mandant_id=$($m.id)", "name=Rathaus $($m.name)") | Out-Null
    Senden '/leitungen/speichern' @("mandant_id=$($m.id)", "bezeichnung=WAN $($m.name)",
        'art=WAN', 'technologie=Glasfaser', 'status=aktiv', 'kosten_monatlich=500') | Out-Null
}
$leitungen = (curl.exe -s -b $jar -c $jar "$b/api/leitungen") | ConvertFrom-Json
"Administrator sieht : " + ($leitungen.bezeichnung -join ', ')
$fremdeId = ($leitungen | Where-Object { $_.mandant.kennzeichen -eq 'ST-MS' }).id

Write-Host "`n=== Konten anlegen ==="
$startpasswoerter = @{}
foreach ($k in @(
    @{ u = 'mh-ma'; n = 'MH Sachbearbeitung'; r = 'Bearbeiter'; m = $gemeinde.id; sub = '' },
    @{ u = 'kreis-pruefer'; n = 'Kreis Pruefung'; r = 'Leser'; m = $kreis.id; sub = '1' })) {
    $felder = @("benutzername=$($k.u)", "name=$($k.n)", "rolle=$($k.r)", "mandant_id=$($k.m)", 'aktiv=1')
    if ($k.sub) { $felder += 'sieht_untergeordnete=1' }
    $status = Senden '/verwaltung/benutzer/speichern' $felder
    $seite = (curl.exe -s -b $jar -c $jar "$b/verwaltung/benutzer") -join "`n"
    if ($seite -match 'Startpasswort fuer\s+([\w-]+):</strong>\s*<code>([^<]+)</code>') {
        $startpasswoerter[$Matches[1]] = $Matches[2]
        "{0,-16} -> {1}, Startpasswort {2}" -f $k.u, $status, $Matches[2]
    } else { "{0,-16} -> {1}" -f $k.u, $status }
}

Write-Host "`n=== Protokoll (Administrator) ==="
$audit = (curl.exe -s -b $jar -c $jar "$b/verwaltung/audit") -join "`n"
foreach ($a in 'anmeldung', 'passwort_geaendert', 'mandant_gespeichert', 'benutzer_gespeichert', 'gespeichert') {
    "  $a : " + ($audit -match ">$a<")
}

Write-Host "`n=== Bearbeiter der Gemeinde ==="
Remove-Item $jar -ErrorAction SilentlyContinue
$pw = $startpasswoerter['mh-ma']
Anmelden 'mh-ma' $pw | Out-Null
$neu2 = 'Gemeinde!Test2026'
Senden '/passwort' @("altes_passwort=$pw", "neues_passwort=$neu2", "wiederholung=$neu2") | Out-Null
$eigene = (curl.exe -s -b $jar -c $jar "$b/api/leitungen") | ConvertFrom-Json
"Sichtbare Leitungen : " + ($eigene.bezeichnung -join ', ')
"Fremde Leitung #$fremdeId  -> " + (Code "/api/leitungen/$fremdeId") + " (erwartet 404)"
"Schreiben in Stadt  -> " + (Senden '/standorte/speichern' @("mandant_id=$($stadt.id)", 'name=Unzulaessig')) + " (erwartet 403)"
"Verwaltung          -> " + (Code '/verwaltung/benutzer') + " (erwartet 403)"
"CSV-Export enthaelt nur eigene: " + ((((curl.exe -s -b $jar -c $jar "$b/leitungen/export.csv") -join '') -match 'Musterhausen') -and
    -not (((curl.exe -s -b $jar -c $jar "$b/leitungen/export.csv") -join '') -match 'WAN Musterstadt'))

Write-Host "`n=== Kreis mit Sicht auf untergeordnete Mandanten ==="
Remove-Item $jar -ErrorAction SilentlyContinue
$pw3 = $startpasswoerter['kreis-pruefer']
Anmelden 'kreis-pruefer' $pw3 | Out-Null
$neu3 = 'Kreis!Pruefung2026'
Senden '/passwort' @("altes_passwort=$pw3", "neues_passwort=$neu3", "wiederholung=$neu3") | Out-Null
$sicht = (curl.exe -s -b $jar -c $jar "$b/api/leitungen") | ConvertFrom-Json
"Kreis sieht         : " + ($sicht.bezeichnung -join ', ')
"Leser schreibt      -> " + (Senden '/standorte/speichern' @("mandant_id=$($kreis.id)", 'name=Darf nicht')) + " (erwartet 403)"

Write-Host "`n=== Kontosperre nach Fehlversuchen ==="
Remove-Item $jar -ErrorAction SilentlyContinue
1..5 | ForEach-Object { Anmelden 'mh-ma' 'falsch' | Out-Null }
$t = Token
$antwort = (& curl.exe -s -c $jar -b $jar -w "`nSTATUS=%{http_code}" -X POST "$b/login" `
    --data-urlencode 'benutzername=mh-ma' --data-urlencode "passwort=$neu2" `
    --data-urlencode "csrf_token=$t") -join "`n"
($antwort -split "`n" | Select-String 'STATUS=').ToString()
"Sperrhinweis        : " + ($antwort -match 'gesperrt')

Remove-Item $jar -ErrorAction SilentlyContinue
