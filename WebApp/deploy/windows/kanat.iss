; KANAT's Windows installer (Inno Setup 6), compiled by build-installer.ps1:
;   ISCC /DAppVersion=0.1.0 /DRunMode=threads /DStageDir=... kanat.iss
; One installer per Detection Service run mode: "threads" (every camera's Run a
; thread of one process, one shared model) or "processes" (a process each, a
; model each). Both are the same product: one installed over the other changes
; the mode and keeps the data.
;
; The installer copies the files (StageDir, built by build-installer.ps1), then
; scripts\install-services.ps1 sets the PC up and starts KANAT's three
; background tasks. Nothing is downloaded: the PC can be offline.

#ifndef AppVersion
  #error AppVersion is not defined: compile with build-installer.ps1
#endif
#ifndef StageDir
  #error StageDir is not defined: compile with build-installer.ps1
#endif
#ifndef OutDir
  #define OutDir "build\output"
#endif
#ifndef RunMode
  #define RunMode "threads"
#endif
#if RunMode != "threads" && RunMode != "processes"
  #error RunMode must be threads or processes
#endif

[Setup]
; The same for both modes and every version: an install replaces the one before it
AppId={{B2F5C1A0-6C1E-4B6E-9B51-7C2D4E1A9F30}
AppName=KANAT
AppVersion={#AppVersion}
AppVerName=KANAT {#AppVersion} ({#RunMode})
AppPublisher=Asgard
DefaultDirName={autopf}\KANAT
DefaultGroupName=KANAT
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\app\KANAT.exe
UninstallDisplayName=KANAT
OutputDir={#OutDir}
OutputBaseFilename=KANAT-Setup-{#AppVersion}-{#RunMode}
; Windows 10 22H2 or 11, 64-bit
MinVersion=10.0.19045
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
SetupLogging=yes
; The scripts stop what runs, as they need to (and the app, which runs from this folder)
CloseApplications=no
RestartApplications=no
; The files are mostly PyTorch's: libraries that compress once, so no solid block
Compression=lzma2/max
SolidCompression=no
LZMANumBlockThreads=8
#ifdef Spanning
DiskSpanning=yes
#endif

[Tasks]
Name: desktopicon; Description: "A KANAT shortcut on the desktop"
Name: autostart; Description: "Open KANAT when Windows starts"

[Dirs]
; The database, the logs and kanat-config.json: kept when KANAT is updated or removed
Name: "{commonappdata}\Kanat"; Permissions: users-modify
Name: "{commonappdata}\Kanat\logs"; Permissions: users-modify

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\KANAT"; Filename: "{app}\app\KANAT.exe"
Name: "{autodesktop}\KANAT"; Filename: "{app}\app\KANAT.exe"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KANAT"; \
    ValueData: """{app}\app\KANAT.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\app\KANAT.exe"; Description: "Open KANAT"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
; Before the files go: the tasks, the processes (the app too) and the firewall rules
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
    Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\uninstall-services.ps1"" -InstallDir ""{app}"""; \
    Flags: runhidden waituntilterminated; RunOnceId: "KanatServices"

[Code]
var
  AdapterPage: TInputOptionWizardPage;
  AdapterNames: TArrayOfString;

function PowerShell(const Parameters: String; var Code: Integer): Boolean;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass ' + Parameters, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

{ The adapter named on the command line (/CameraAdapter="Ethernet 2"), else the one chosen on the page }
function CameraAdapter: String;
var
  Index: Integer;
begin
  Result := ExpandConstant('{param:CameraAdapter|}');
  if (Result = '') and (AdapterPage <> nil) then
  begin
    Index := AdapterPage.SelectedValueIndex;
    if (Index > 0) and (Index <= GetArrayLength(AdapterNames)) then
      Result := AdapterNames[Index - 1];
  end;
end;

procedure InitializeWizard;
var
  ListFile: String;
  Lines: TArrayOfString;
  Code, I: Integer;
begin
  AdapterPage := CreateInputOptionPage(wpSelectDir, 'The cameras',
    'Which network adapter are the cameras on?',
    'KANAT sends the cameras'' multicast video to this adapter and sets it to the Private network profile. ' +
    'With a single adapter, let Windows choose.', True, False);
  AdapterPage.Add('Let Windows choose');
  ListFile := ExpandConstant('{tmp}\adapters.txt');
  if PowerShell('-Command "Get-NetAdapter -Physical | Where-Object Status -eq ''Up'' | ForEach-Object { $_.Name } | Set-Content -Encoding Default ''' + ListFile + '''"', Code)
     and (Code = 0) and LoadStringsFromFile(ListFile, Lines) then
  begin
    for I := 0 to GetArrayLength(Lines) - 1 do
      if Trim(Lines[I]) <> '' then
      begin
        SetArrayLength(AdapterNames, GetArrayLength(AdapterNames) + 1);
        AdapterNames[GetArrayLength(AdapterNames) - 1] := Trim(Lines[I]);
        AdapterPage.Add(Trim(Lines[I]));
      end;
  end;
  AdapterPage.SelectedValueIndex := 0;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { No question to ask a silent install, or one told the adapter, or a PC with no adapter to choose from }
  Result := (PageID = AdapterPage.ID) and (WizardSilent or (ExpandConstant('{param:CameraAdapter|}') <> '') or (GetArrayLength(AdapterNames) = 0));
end;

{ Stops what runs from the folder being updated, so its files can be replaced }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Script: String;
  Code: Integer;
begin
  Result := '';
  Script := ExpandConstant('{app}\scripts\uninstall-services.ps1');
  if FileExists(Script) then
    PowerShell('-File "' + Script + '" -InstallDir "' + ExpandConstant('{app}') + '" -StopOnly', Code);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Adapter: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Setting KANAT up and starting it (a minute or two)...';
    Adapter := CameraAdapter;
    if (not PowerShell('-File "' + ExpandConstant('{app}\scripts\install-services.ps1') + '" -InstallDir "' + ExpandConstant('{app}') +
          '" -RunMode {#RunMode} -CameraAdapter "' + Adapter + '"', Code)) or (Code <> 0) then
      SuppressibleMsgBox('KANAT''s files are installed, but setting the PC up failed.' + #13#10 + #13#10 +
        'The last line starting with FAILED in ' + ExpandConstant('{commonappdata}\Kanat\logs\installer.log') +
        ' says what to do. Run the installer again once it is fixed.', mbError, MB_OK, IDOK);
  end;
end;
