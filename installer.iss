; Inno Setup script for PDF Renamer
; Builds a proper Setup.exe that installs the bundled PDF-Renamer.exe and
; creates Start Menu + (optional) Desktop shortcuts.
;
; How to build:
;   1) Install Inno Setup (free): https://jrsoftware.org/isdl.php
;   2) Open this file in Inno Setup and click "Compile"  (or run: iscc installer.iss)
;   3) The installer appears in:  installer_output\PDF-Renamer-Setup.exe
;
; Note: build dist\PDF-Renamer.exe first (see Derle-EXE.bat).

#define MyAppName "PDF Renamer"
#define MyAppVersion "2.0"
#define MyAppPublisher "Yavuz Zeynula"
#define MyAppExe "PDF-Renamer.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=PDF-Renamer-Setup
SetupIconFile=assets\app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Kullanici bazinda kurulum: admin gerekmez VE kurulum klasoru yazilabilir
; olur (otomatik guncelleyici src/'yi buraya yazar). {autopf} bu modda
; {localappdata}\Programs altina cozulur.
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Tum launcher klasoru (exe + _internal + src/) kurulur.
Source: "dist\PDF-Renamer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
