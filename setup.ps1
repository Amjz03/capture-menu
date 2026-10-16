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
# Shortcuts start Python (or CaptureMenu.exe) directly: nothing in between that can be blocked
# or missing at sign-in. Capture Menu starts OBS itself when it isn't running.
$exe = Join-Path $here "CaptureMenu.exe"
if (Test-Path $exe) {
    $target = $exe; $arguments = ""
} else {
    $python = (& py -3 -c "import sys; print(sys.executable)").Trim()
    $target = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    $arguments = "`"$(Join-Path $here 'capture_menu.py')`""
}
if (-not (Test-Path $target)) {
    Write-Host "   Couldn't find $target" -ForegroundColor Red; exit 1
}
$shell = New-Object -ComObject WScript.Shell
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Capture Menu.lnk"
$targets = @(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Capture Menu.lnk"),
    $startup
)
foreach ($lnk in $targets) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $target
    $s.Arguments = $arguments
    $s.WorkingDirectory = $here
    $s.Description = "Capture Menu"
    $s.Save()
}
# Windows keeps a per-app "allowed to start" switch (Task Manager > Startup apps); make sure it's on
$approved = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
if (Test-Path $approved) {
    Remove-ItemProperty -Path $approved -Name "Capture Menu.lnk" -ErrorAction SilentlyContinue
}
Write-Host "   Start menu + starts with Windows"

Step "Starting Capture Menu"
if ($arguments) { Start-Process -FilePath $target -ArgumentList $arguments -WorkingDirectory $here }
else { Start-Process -FilePath $target -WorkingDirectory $here }
Write-Host ""
Write-Host "All set. Press Alt + C (or Create on your controller) while playing." -ForegroundColor Green
Write-Host "The first time, Capture Menu sets up OBS for your PC and restarts it once."
