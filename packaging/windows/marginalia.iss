; The Windows installer (ADR 0028). packaging/build.py compiles it with Inno Setup 6:
;   ISCC /DAppVersion=0.2.0 /DSourceDir=dist\Marginalia /DOutputDir=dist /DIconFile=packaging\build\icon.ico marginalia.iss
; It installs for the current user only, so it needs no administrator rights, and the app can
; update itself by running a newer copy of this installer with /SILENT.

#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z
#endif

[Setup]
; Never change the AppId: it is how a newer installer finds the install it is updating.
AppId={{B24531FC-C7FE-4FCC-A4A0-1844BE9FB118}
AppName=Marginalia
AppVersion={#AppVersion}
AppVerName=Marginalia {#AppVersion}
AppPublisher=Marginalia
AppPublisherURL=https://github.com/amoghdprasanna/marginalia
PrivilegesRequired=lowest
; In a per-user install {autopf} is %LOCALAPPDATA%\Programs.
DefaultDirName={autopf}\Marginalia
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=Marginalia-{#AppVersion}-windows-setup
#ifdef IconFile
SetupIconFile={#IconFile}
#endif
UninstallDisplayIcon={app}\Marginalia.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The bundled libraries change between versions; don't leave the old ones beside the new.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Marginalia"; Filename: "{app}\Marginalia.exe"
Name: "{autodesktop}\Marginalia"; Filename: "{app}\Marginalia.exe"; Tasks: desktopicon

[Run]
; A checkbox at the end of a normal install; after a silent update it simply starts the app.
Filename: "{app}\Marginalia.exe"; Description: "{cm:LaunchProgram,Marginalia}"; Flags: nowait postinstall

[Code]
// Settings > "Open Marginalia when you log in" writes this value (src/marginalia/autostart.py).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Marginalia');
end;
