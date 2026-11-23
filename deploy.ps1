# Compatible with Windows PowerShell 5.1 and PowerShell 7.
# Reuse installed Python >=3.9,<4.0. Never download or install a runtime.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$ai4sRoot = $PSScriptRoot
$ai4sProbe = 'import sys,sqlite3,ssl,http.server,ctypes; assert (3,9)<=sys.version_info[:2]<(4,0); print(sys.executable)'
$ai4sPython = $null
$ai4sCandidates = @()
if ($env:VIRTUAL_ENV) { $ai4sCandidates += (Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe') }
$ai4sCandidates += (Join-Path $ai4sRoot '.venv/Scripts/python.exe')
foreach ($ai4sName in @('python','python3')) {
    $ai4sCommand = Get-Command $ai4sName -ErrorAction SilentlyContinue
    if ($ai4sCommand) { $ai4sCandidates += $ai4sCommand.Source }
}
foreach ($ai4sCandidate in ($ai4sCandidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $ai4sCandidate -PathType Leaf)) { continue }
    try {
        $ai4sResult = & $ai4sCandidate -X utf8 -c $ai4sProbe 2>$null
        if ($LASTEXITCODE -eq 0 -and $ai4sResult) { $ai4sPython = [string]($ai4sResult | Select-Object -Last 1); break }
    } catch { continue }
}
if (-not $ai4sPython -and (Get-Command py -ErrorAction SilentlyContinue)) {
    try {
        $ai4sResult = & py -3 -X utf8 -c $ai4sProbe 2>$null
        if ($LASTEXITCODE -eq 0 -and $ai4sResult) { $ai4sPython = [string]($ai4sResult | Select-Object -Last 1) }
    } catch {}
}
if (-not $ai4sPython) {
    Write-Error 'No compatible Python found. Required: Python >=3.9,<4.0 with sqlite3, ssl, http.server and ctypes. Install a compatible Python or invoke deploy.py with its full interpreter path. No system settings were changed.'
    exit 1
}
& $ai4sPython -B -X utf8 (Join-Path $ai4sRoot 'deploy.py') @args
exit $LASTEXITCODE
