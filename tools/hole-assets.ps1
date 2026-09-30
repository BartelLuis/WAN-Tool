$ErrorActionPreference = 'Stop'
$ziel = Join-Path $PSScriptRoot 'app\static\vendor'
New-Item -ItemType Directory -Force -Path $ziel | Out-Null
$url = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css'
$datei = Join-Path $ziel 'bootstrap.min.css'
for ($i = 1; $i -le 5; $i++) {
    try {
        Invoke-WebRequest $url -OutFile $datei -UseBasicParsing -TimeoutSec 60
        break
    } catch {
        Write-Host "Versuch $i fehlgeschlagen: $_"
        if ($i -eq 5) { throw }
    }
}
$hash = (Get-FileHash $datei -Algorithm SHA256).Hash.ToLower()
# LF ohne BOM, damit `sha256sum --check` unter Linux die Datei lesen kann.
[IO.File]::WriteAllText(
    (Join-Path $ziel 'SHA256SUMS'),
    "$hash  bootstrap.min.css`n",
    (New-Object Text.UTF8Encoding $false)
)
"Groesse: $((Get-Item $datei).Length) Bytes"
"SHA256 : $hash"
