$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..

New-Item -ItemType Directory -Force -Path secrets | Out-Null

function Zufall([int]$laenge) {
    $bytes = New-Object byte[] $laenge
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [Convert]::ToBase64String($bytes) -replace '[+/=]', 'x'
}

$dbPass = Zufall 24
$rootPass = Zufall 24
$sessionSecret = Zufall 48
$adminPass = (Zufall 12) + 'Aa1!'

[IO.File]::WriteAllText("$PWD\secrets\mysql_root_password", $rootPass)
[IO.File]::WriteAllText("$PWD\secrets\mysql_password", $dbPass)

@"
MYSQL_DATABASE=wantool
MYSQL_USER=wantool
MYSQL_PASSWORD=$dbPass
SESSION_SECRET=$sessionSecret
ADMIN_BENUTZER=admin
ADMIN_PASSWORT=$adminPass
BEHOERDE=Kreis Musterland
UMGEBUNG=produktion
COOKIE_SECURE=false
ERLAUBTE_HOSTS=*
DOCS_AKTIV=false
APP_PORT=8000
START_MANDANT_NAME=Musterland
START_MANDANT_KENNZEICHEN=KR-ML
START_MANDANT_ART=Kreis
"@ | Set-Content .env -NoNewline

"Administratorpasswort: $adminPass"
