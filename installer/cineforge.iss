; Inno Setup script for CineForge. Build with:  iscc /DAppVersion=0.1.0 installer\cineforge.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{7E2B5C0A-4F3D-4C57-9A41-C1AEF0B6E001}
AppName=CineForge
AppVersion={#AppVersion}
AppPublisher=CineForge contributors
DefaultDirName={autopf}\CineForge
DefaultGroupName=CineForge
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=..\installer_out
OutputBaseFilename=CineForge-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\CineForge.exe
UninstallDisplayName=CineForge
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\CineForge\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\build\ffmpeg-buildinfo.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\CineForge"; Filename: "{app}\CineForge.exe"
Name: "{group}\Uninstall CineForge"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CineForge"; Filename: "{app}\CineForge.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CineForge.exe"; Description: "Launch CineForge"; Flags: nowait postinstall skipifsilent
