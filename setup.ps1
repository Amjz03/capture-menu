# Capture Menu one-click setup: installs what it needs, connects OBS, adds shortcuts, starts it.
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8 = New-Object System.Text.UTF8Encoding $false   # JSON without a BOM

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

function Install-Package($id, $label) {
    Write-Host "   $label ..." -NoNewline
    winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements *> $null
    # winget exits non-zero when it's already installed, which is fine
    Write-Host " done"
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "winget isn't available. Install 'App Installer' from the Microsoft Store, then run Setup again." -ForegroundColor Red
    exit 1
}

Step "Installing Python, OBS Studio and FFmpeg"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { Install-Package "Python.Python.3.12" "Python 3.12" }
else { Write-Host "   Python already installed" }
Install-Package "OBSProject.OBSStudio" "OBS Studio"
Install-Package "Gyan.FFmpeg" "FFmpeg"
# pick up the new PATH entries without reopening the window
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

Step "Installing Capture Menu's Python libraries"
py -3 -m pip install --disable-pip-version-check -q --upgrade -r "$here\requirements.txt"
if ($LASTEXITCODE -ne 0) { Write-Host "   pip failed, see the messages above." -ForegroundColor Red; exit 1 }

Step "Connecting OBS"
# OBS rewrites its settings when it exits, so close it politely first
$obs = Get-Process obs64 -ErrorAction SilentlyContinue
if ($obs) {
    $obs | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    $obs | Wait-Process -Timeout 20 -ErrorAction SilentlyContinue
}
$wsDir = Join-Path $env:APPDATA "obs-studio\plugin_config\obs-websocket"
New-Item -ItemType Directory -Force $wsDir | Out-Null
$wsFile = Join-Path $wsDir "config.json"
$ws = if (Test-Path $wsFile) { Get-Content $wsFile -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
$password = $ws.server_password
if (-not $password) {
    $chars = [char[]]((48..57) + (65..90) + (97..122))
    $password = -join (1..20 | ForEach-Object { $chars | Get-Random })
}
$port = if ($ws.server_port) { $ws.server_port } else { 4455 }
foreach ($kv in @{ server_enabled = $true; auth_required = $true; server_password = $password;
                    server_port = $port; first_load = $false; alerts_enabled = $false }.GetEnumerator()) {
    $ws | Add-Member -NotePropertyName $kv.Key -NotePropertyValue $kv.Value -Force
}
[IO.File]::WriteAllText($wsFile, ($ws | ConvertTo-Json), $utf8)

# OBS opens its Auto-Configuration Wizard on the very first start. Capture Menu sets OBS up
# itself, so mark that first start as done and OBS stays quietly in the tray.
function Set-IniValue($file, $section, $key, $value) {
    $lines = if (Test-Path $file) { @(Get-Content $file) } else { @() }
    $out = New-Object System.Collections.Generic.List[string]
    $inSection = $false; $done = $false
    foreach ($line in $lines) {
        if ($line -match '^\[(.+)\]$') {
            if ($inSection -and -not $done) { $out.Add("$key=$value"); $done = $true }
            $inSection = ($Matches[1] -eq $section)
        } elseif ($inSection -and $line -match "^$key=") { $out.Add("$key=$value"); $done = $true; continue }
        $out.Add($line)
    }
    if (-not $done) {
        if (-not $inSection) { $out.Add("[$section]") }
        $out.Add("$key=$value")
    }
    [IO.File]::WriteAllLines($file, $out, $utf8)
}
$obsDir = Join-Path $env:APPDATA "obs-studio"
# OBS 31+ keeps these in user.ini and copies global.ini over the first time, so only touch
# user.ini once it exists; a fresh install gets global.ini, which OBS 31 then takes over.
$inis = @("global.ini")
if (Test-Path (Join-Path $obsDir "user.ini")) { $inis += "user.ini" }
New-Item -ItemType Directory -Force $obsDir | Out-Null
foreach ($ini in $inis) {
    Set-IniValue (Join-Path $obsDir $ini) "General" "FirstRun" "false"
    Set-IniValue (Join-Path $obsDir $ini) "BasicWindow" "SysTrayEnabled" "true"
    Set-IniValue (Join-Path $obsDir $ini) "BasicWindow" "SysTrayWhenStarted" "true"
}

$cfgFile = Join-Path $here "config.json"
$cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
$cfg.obs_password = $password
$cfg.obs_port = $port
[IO.File]::WriteAllText($cfgFile, ($cfg | ConvertTo-Json -Depth 5), $utf8)
Write-Host "   WebSocket on, password saved to config.json"

Step "Adding shortcuts"
$shell = New-Object -ComObject WScript.Shell
$launcher = Join-Path $here "CaptureMenu.vbs"
$targets = @(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Capture Menu.lnk"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Capture Menu.lnk")
)
foreach ($lnk in $targets) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = "wscript.exe"
    $s.Arguments = "`"$launcher`""
    $s.WorkingDirectory = $here
    $s.Description = "Capture Menu"
    $s.Save()
}
Write-Host "   Start menu + starts with Windows"

Step "Starting Capture Menu"
Start-Process wscript.exe "`"$launcher`""
Write-Host ""
Write-Host "All set. Press Alt + C (or Create on your controller) while playing." -ForegroundColor Green
Write-Host "The first time, Capture Menu sets up OBS for your PC and restarts it once."
Write-Host "If OBS asks to run its Auto-Configuration Wizard, choose No."
