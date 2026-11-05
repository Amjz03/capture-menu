# Removes Capture Menu: stops it, deletes its shortcuts and its install folder.
# Captures (Videos\Capture Menu Clips by default), the player's own OBS Studio, FFmpeg and Python stay.
$programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcuts = @((Join-Path $programs "Capture Menu.lnk"), (Join-Path $programs "Startup\Capture Menu.lnk"))

function Is-AppFolder($dir) {
    $dir -and ((Test-Path (Join-Path $dir "capture_menu.py")) -or (Test-Path (Join-Path $dir "CaptureMenu.exe")))
}

# The install folder is wherever the Start menu shortcut points; fall back to this script's folder
$dir = $null
$shell = New-Object -ComObject WScript.Shell
foreach ($lnk in $shortcuts) {
    if (Test-Path $lnk) { $dir = $shell.CreateShortcut($lnk).WorkingDirectory; break }
}
if (-not (Is-AppFolder $dir)) { $dir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not (Is-AppFolder $dir)) {
    Write-Host "Couldn't find Capture Menu on this PC." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  This removes Capture Menu from $dir" -ForegroundColor White
Write-Host "  Your captures, your own OBS Studio and FFmpeg are kept." -ForegroundColor Gray
$answer = Read-Host "  Type Y and press Enter to remove it"
if ($answer -notmatch '^[yY]') { Write-Host "  Nothing was removed."; exit 0 }

Remove-Item "$env:LOCALAPPDATA\CaptureMenu\alive" -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "CaptureMenu.exe" -or
                   ($_.Name -like "python*.exe" -and $_.CommandLine -like "*capture_menu.py*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
foreach ($lnk in $shortcuts) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue }
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Capture Menu" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "Capture Menu ($env:USERNAME)" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "Capture Menu watch ($env:USERNAME)" -Confirm:$false -ErrorAction SilentlyContinue
# Capture Menu's own OBS runs from AppData\CaptureMenu and records the last minutes there: stop only
# that one (the player's own OBS is left alone), then remove them
Get-CimInstance Win32_Process -Filter "Name = 'obs64.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$env:LOCALAPPDATA\CaptureMenu\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1   # its files are let go once it's ended
Start-Sleep -Seconds 1
Remove-Item "$env:LOCALAPPDATA\CaptureMenu" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "  Stopped it and removed the shortcuts." -ForegroundColor Green

# This window may be running from that folder, so a hidden helper deletes it a few seconds later
Start-Process cmd.exe -WindowStyle Hidden -WorkingDirectory $env:TEMP `
    -ArgumentList "/c ping -n 4 127.0.0.1 >nul & rmdir /s /q `"$dir`""
Write-Host "  Capture Menu is removed (its folder goes in a few seconds)." -ForegroundColor Green
