; CaptureMenu-Setup.exe: installs the built CaptureMenu.exe (dist\CaptureMenu from installer\build_exe.bat),
; then runs setup.ps1 to download its own OBS, install FFmpeg, connect OBS, add the shortcuts and start it.
; Build (from the repo root): iscc /DAppVersion=0.0.1 installer\installer.iss   ->   Output\CaptureMenu-Setup.exe
; Test switch: CaptureMenu-Setup.exe /NOSETUP copies the files only (no OBS, shortcuts or start).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0C2D4B-7A51-4C8E-9B3F-CA9E3D1F2A60}
AppName=Capture Menu
AppVersion={#AppVersion}
AppPublisher=Amjz03
AppPublisherURL=https://github.com/Amjz03/capture-menu
DefaultDirName={localappdata}\Programs\CaptureMenu
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
SourceDir=..
OutputDir=Output
OutputBaseFilename=CaptureMenu-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\CaptureMenu.exe
UninstallDisplayName=Capture Menu
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=no

[Messages]
WelcomeLabel2=This installs Capture Menu, a PS5-style Create button for Windows.%n%nIt also downloads its own copy of OBS Studio (your own OBS, if you have one, isn't touched) and installs FFmpeg if you don't have it. This takes a few minutes the first time.
FinishedLabel=Capture Menu is installed and running (its icon is next to the clock).%n%nPress Alt + C in a game, or Create on your controller.

[Files]
Source: "dist\CaptureMenu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer\setup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
; keep a friend's settings (and the OBS password) when they update
Source: "config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | ? {{ $_.Name -eq 'CaptureMenu.exe' -or ($_.Name -like 'python*.exe' -and $_.CommandLine -like '*capture_menu.py*') } | % {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "StopCaptureMenu"
; setup.ps1 adds a sign-in task and a Run entry so Capture Menu starts with Windows
Filename: "reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""Capture Menu"" /f"; Flags: runhidden; RunOnceId: "RemoveStartWithWindows"
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Capture Menu ({username})"" /F"; Flags: runhidden; RunOnceId: "RemoveSignInTask"
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Capture Menu watch ({username})"" /F"; Flags: runhidden; RunOnceId: "RemoveWatchTask"
; Capture Menu's own OBS runs from {localappdata}\CaptureMenu and records the last minutes there: stop it so
; they can go (only that one: the player's own OBS is left alone). CIM, not Get-Process: this is 32-bit
; PowerShell, where Get-Process can't read a 64-bit program's path. Keep this RunOnceId: an update keeps
; the older entry with it (0.0.41's taskkill /F /IM obs64.exe, which closed the player's OBS too), and
; only one entry per RunOnceId runs.
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | ? {{ $_.Name -eq 'obs64.exe' -and $_.ExecutablePath -like ($env:LOCALAPPDATA + '\CaptureMenu\*') } | % {{ Stop-Process -Id $_.ProcessId -Force }; Start-Sleep 1"""; Flags: runhidden; RunOnceId: "StopObsRecording"

[UninstallDelete]
; setup.ps1 makes these; captures in Videos\Capture Menu Clips are never touched
Type: files; Name: "{userprograms}\Capture Menu.lnk"
Type: files; Name: "{userstartup}\Capture Menu.lnk"
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{localappdata}\CaptureMenu"

[Code]
function NoSetup: Boolean;
begin
  Result := Pos('/NOSETUP', UpperCase(GetCmdTail)) > 0;
end;

procedure StopCaptureMenu;
var
  Code: Integer;
begin
  // Capture Menu stops, and files are replaced once it's really gone. Its OBS runs from its own folder
  // (setup.ps1 stops it only when it replaces that), and the player's own OBS is never touched.
  Exec('powershell.exe', '-NoProfile -Command "Get-CimInstance Win32_Process | ? { $_.Name -eq ''CaptureMenu.exe'' -or ($_.Name -like ''python*.exe'' -and $_.CommandLine -like ''*capture_menu.py*'') } | % { Stop-Process -Id $_.ProcessId -Force }; foreach ($i in 1..80) { if (-not (Get-Process CaptureMenu -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Milliseconds 250 }"',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if not NoSetup then
    StopCaptureMenu;   // an older copy may hold its files open
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Log: String;
begin
  if (CurStep <> ssPostInstall) or NoSetup then
    Exit;
  WizardForm.StatusLabel.Caption := 'Downloading OBS Studio, installing FFmpeg and connecting OBS. This can take a few minutes...';
  WizardForm.ProgressGauge.Style := npbstMarquee;
  try
    if not Exec('powershell.exe',
                '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\setup.ps1') + '" -InstallDir "' + ExpandConstant('{app}') + '"',
                ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
      Code := -1;
  finally
    WizardForm.ProgressGauge.Style := npbstNormal;
  end;
  if Code <> 0 then
  begin
    Log := ExpandConstant('{app}\setup.log');
    if MsgBox('Capture Menu is installed, but something still needs attention (for example OBS or FFmpeg didn''t install).' + #13#10#13#10 +
              'Open the setup log to see what to fix? Running CaptureMenu-Setup.exe again usually sorts it out.',
              mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('', 'notepad.exe', '"' + Log + '"', '', SW_SHOWNORMAL, ewNoWait, Code);
  end;
end;
