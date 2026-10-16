# Capture Menu one-click setup: installs what it needs, copies the app to a fixed folder,
# connects OBS, adds shortcuts, starts it, then checks that everything is ready.
# Running it again updates an existing install and keeps its settings.
param([string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\CaptureMenu"))

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8 = New-Object System.Text.UTF8Encoding $false   # JSON without a BOM
$total = 7
$script:step = 0

function Step($text) {
    $script:step++
    Write-Host ""
    Write-Host "[$script:step/$total] $text" -ForegroundColor Cyan
}
function Ok($text)   { Write-Host "   OK  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "   !!  $text" -ForegroundColor Yellow }
function Fail($text) {
    Write-Host ""
    Write-Host "   Setup stopped: $text" -ForegroundColor Red
    exit 1
}

function Install-Package($id, $label) {
    Write-Host "   $label ..." -NoNewline
    winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements *> $null
    # winget exits non-zero when it's already installed, which is fine
    Write-Host " done"
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

# A Python that really runs (not the Microsoft Store stub that only opens the Store)
function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $p = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
        if ($p) { $candidates += $p.Trim() }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $candidates += $cmd.Source }
    $candidates += Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe") -ErrorAction SilentlyContinue |
                   Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            & $c -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        }
    }
    return $null
}

# Same places Capture Menu itself looks
function Find-FFmpeg {
    $local = Join-Path $InstallDir "ffmpeg.exe"
    if (Test-Path $local) { return $local }
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $winget = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet"
    $link = Join-Path $winget "Links\ffmpeg.exe"
    if (Test-Path $link) { return $link }
    $pkg = Get-ChildItem (Join-Path $winget "Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe") -ErrorAction SilentlyContinue |
           Sort-Object FullName -Descending | Select-Object -First 1
    if ($pkg) { return $pkg.FullName }
    return $null
}

function Find-OBS {
    foreach ($key in "HKLM:\SOFTWARE\OBS Studio", "HKCU:\SOFTWARE\OBS Studio") {
        $dir = (Get-ItemProperty $key -ErrorAction SilentlyContinue).'(default)'
        if ($dir -and (Test-Path (Join-Path $dir "bin\64bit\obs64.exe"))) { return Join-Path $dir "bin\64bit\obs64.exe" }
    }
    $default = Join-Path $env:ProgramFiles "obs-studio\bin\64bit\obs64.exe"
    if (Test-Path $default) { return $default }
    return $null
}

function Stop-CaptureMenu {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "CaptureMenu.exe" -or
                       ($_.Name -like "python*.exe" -and $_.CommandLine -like "*capture_menu.py*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "  Capture Menu setup" -ForegroundColor White
Write-Host "  This takes a few minutes the first time. Leave this window open." -ForegroundColor Gray

New-Item -ItemType Directory -Force $InstallDir | Out-Null
Start-Transcript -Path (Join-Path $InstallDir "setup.log") -Force | Out-Null   # CaptureMenu-Setup.exe shows it if something's off

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Fail "winget isn't available. Install 'App Installer' from the Microsoft Store, then run Setup again."
}

# ---------------------------------------------------------------- 1. copy the app
Step "Copying Capture Menu to $InstallDir"
$sameDir = (Resolve-Path $here).Path.TrimEnd('\') -ieq [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if ($sameDir) {
    Ok "Already in place"
} else {
    Stop-CaptureMenu   # an older copy may be running from there
    New-Item -ItemType Directory -Force $InstallDir | Out-Null
    $keepConfig = Test-Path (Join-Path $InstallDir "config.json")
    $skip = @(".git", ".github", ".gitignore", "tests", "docs", "__pycache__", ".thumbs", "state.json")
    Get-ChildItem $here -Force | Where-Object { $_.Name -notin $skip -and $_.Extension -ne ".log" } | ForEach-Object {
        if ($_.Name -eq "config.json" -and $keepConfig) { return }   # updating: keep their settings
        Copy-Item $_.FullName -Destination $InstallDir -Recurse -Force
    }
    if ($keepConfig) { Ok "Updated, your settings are kept" } else { Ok "Copied" }
}
Get-ChildItem $InstallDir -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- 2. programs
Step "Installing Python, OBS Studio and FFmpeg (skips what you already have)"
$exe = Join-Path $InstallDir "CaptureMenu.exe"
$frozen = Test-Path $exe
if ($frozen) {
    Write-Host "   Python not needed (standalone CaptureMenu.exe)"
} elseif (Find-Python) {
    Write-Host "   Python already installed"
} else {
    Install-Package "Python.Python.3.12" "Python 3.12"
}
if (Find-OBS) { Write-Host "   OBS Studio already installed" } else { Install-Package "OBSProject.OBSStudio" "OBS Studio" }
if (Find-FFmpeg) { Write-Host "   FFmpeg already installed" } else { Install-Package "Gyan.FFmpeg" "FFmpeg" }
Refresh-Path   # pick up the new PATH entries without reopening the window

# ---------------------------------------------------------------- 3. python libraries
Step "Installing Capture Menu's Python libraries"
$python = $null
if ($frozen) {
    Ok "Not needed"
} else {
    $python = Find-Python
    if (-not $python) { Fail "Python didn't install. Restart the PC and run Setup again." }
    & $python -m pip install --disable-pip-version-check -q --upgrade -r (Join-Path $InstallDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Fail "pip couldn't install the libraries (see the messages above). Check the internet connection and run Setup again." }
    Ok "Libraries ready"
}

# ---------------------------------------------------------------- 4. OBS websocket
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

$cfgFile = Join-Path $InstallDir "config.json"
$cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
$cfg.obs_password = $password
$cfg.obs_port = $port
[IO.File]::WriteAllText($cfgFile, ($cfg | ConvertTo-Json -Depth 5), $utf8)
Ok "WebSocket on, password saved to config.json"

# ---------------------------------------------------------------- 5. shortcuts
Step "Adding Capture Menu to the Start menu and Windows startup"
# Shortcuts start Python (or CaptureMenu.exe) directly: nothing in between that can be blocked
# or missing at sign-in. Capture Menu starts OBS itself when it isn't running.
if ($frozen) {
    $target = $exe; $arguments = ""
} else {
    $target = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    $arguments = "`"$(Join-Path $InstallDir 'capture_menu.py')`""
}
if (-not (Test-Path $target)) { Fail "Couldn't find $target" }
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
    $s.WorkingDirectory = $InstallDir
    $s.Description = "Capture Menu"
    $s.Save()
}
# Windows keeps a per-app "allowed to start" switch (Task Manager > Startup apps); make sure it's on
$approved = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
if (Test-Path $approved) {
    Remove-ItemProperty -Path $approved -Name "Capture Menu.lnk" -ErrorAction SilentlyContinue
}
Ok "Start menu + starts with Windows"

# ---------------------------------------------------------------- 6. start
Step "Starting Capture Menu"
Stop-CaptureMenu
if ($arguments) { Start-Process -FilePath $target -ArgumentList $arguments -WorkingDirectory $InstallDir }
else { Start-Process -FilePath $target -WorkingDirectory $InstallDir }
Start-Sleep -Seconds 5

# ---------------------------------------------------------------- 7. check
Step "Checking everything"
$problems = 0
if ($frozen) { Ok "Capture Menu (standalone .exe)" }
else {
    & $python -c "import PySide6, obsws_python, sdl2" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok "Python libraries" } else { Warn "Python libraries didn't load. Run Setup again."; $problems++ }
}
if (Find-OBS) { Ok "OBS Studio" } else { Warn "OBS Studio isn't installed. Install it from obsproject.com, then run Setup again."; $problems++ }
if (Find-FFmpeg) { Ok "FFmpeg (saving, trimming and sharing clips)" } else { Warn "FFmpeg isn't installed, so clips can't be saved. Run Setup again."; $problems++ }
$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -eq "CaptureMenu.exe" -or ($_.Name -like "python*.exe" -and $_.CommandLine -like "*capture_menu.py*") }
if ($running) { Ok "Capture Menu is running (icon next to the clock)" }
else { Warn "Capture Menu didn't start. Look at capture_menu.log in $InstallDir"; $problems++ }

Write-Host ""
if ($problems -eq 0) {
    Write-Host "  All set! Press Alt + C (or Create on your controller) while playing." -ForegroundColor Green
    Write-Host "  The first time, Capture Menu sets up OBS for your PC and restarts it once."
} else {
    Write-Host "  Almost there: fix the item(s) marked !! above, then run Setup again." -ForegroundColor Yellow
}
Write-Host "  Installed in $InstallDir. You can delete the downloaded folder." -ForegroundColor Gray
Stop-Transcript | Out-Null
exit $problems
