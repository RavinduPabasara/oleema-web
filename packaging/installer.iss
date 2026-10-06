; Inno Setup script for Oleema
; Built by .github/workflows/windows-build.yml:  iscc /DAppVersion=1.2.3 packaging\installer.iss
;
; Installs per-user (no admin rights needed). The database and backups live in
; %APPDATA%\Oleema and are kept on uninstall/upgrade.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{9B3E5C1A-7D24-4F6B-8E0C-2A5D7F1B3C88}
AppName=Oleema
AppVersion={#AppVersion}
AppPublisher=Oleema Industries
DefaultDirName={autopf}\Oleema
DefaultGroupName=Oleema
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Oleema-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Oleema.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Oleema\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Oleema"; Filename: "{app}\Oleema.exe"
Name: "{group}\Oleema data folder (database & backups)"; Filename: "{userappdata}\Oleema"
Name: "{group}\Uninstall Oleema"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Oleema"; Filename: "{app}\Oleema.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Oleema.exe"; Description: "{cm:LaunchProgram,Oleema}"; Flags: nowait postinstall skipifsilent
