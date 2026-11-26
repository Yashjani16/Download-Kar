; Inno Setup script for the Windows installer.
; Build from the desktop/ folder after PyInstaller:  iscc /DAppVersion=1.0.0 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.2.2"
#endif

[Setup]
AppId={{6DC326FA-107D-4BE9-9095-7D3A29F33D2F}
AppName=Download Kar
AppVersion={#AppVersion}
AppPublisher=Download Kar
DefaultDirName={localappdata}\Programs\Download Kar
DefaultGroupName=Download Kar
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=DownloadKar-Desktop-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Download Kar.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
LicenseFile=..\LICENSE-RECLIP

[Tasks]
Name: "autostart"; Description: "Start Download Kar when I sign in to Windows (recommended, so the browser extension can always reach it)"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Download Kar\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Download Kar"; Filename: "{app}\Download Kar.exe"
Name: "{userdesktop}\Download Kar"; Filename: "{app}\Download Kar.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Download Kar"; ValueData: """{app}\Download Kar.exe"" --server"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Download Kar.exe"; Description: "Open Download Kar now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM ""Download Kar.exe"""; Flags: runhidden; RunOnceId: "StopApp"
