#ifndef AppVersion
#define AppVersion "1.0.0"
#endif

#ifnexist "dist\Dazzle\Dazzle.exe"
  #error "EXE не найден. Сначала выполните build_exe.ps1."
#endif
#ifnexist "assets\dazzle.ico"
  #error "Иконка не найдена: assets\\dazzle.ico"
#endif
#ifnexist "assets\default_settings.json"
  #error "Пресет настроек не найден: assets\\default_settings.json"
#endif

[Setup]
AppId={{AEB04E34-D4E2-47B4-9D9C-8F889434E89F}
AppName=Dazzle AUTO255 (Windows 10/11)
AppVersion={#AppVersion}
AppPublisher=Dazzle
DefaultDirName={localappdata}\Programs\Dazzle AUTO255
DefaultGroupName=Dazzle AUTO255
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Dazzle-AUTO255-Win10-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Dazzle.exe
SetupIconFile=assets\dazzle.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "Дополнительно:"
Name: "startup"; Description: "Запускать вместе с Windows"; GroupDescription: "Дополнительно:"

[InstallDelete]
; Ярлыки прошлых версий назывались просто «Dazzle» — убираем, чтобы не двоились.
Type: files; Name: "{autoprograms}\Dazzle.lnk"
Type: files; Name: "{autodesktop}\Dazzle.lnk"

[Files]
Source: "dist\Dazzle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\default_settings.json"; DestDir: "{userappdata}\Dazzle"; DestName: "settings.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\Dazzle AUTO255"; Filename: "{app}\Dazzle.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Dazzle AUTO255"; Filename: "{app}\Dazzle.exe"; Tasks: desktopicon; WorkingDir: "{app}"
Name: "{userstartup}\Dazzle"; Filename: "{app}\Dazzle.exe"; Tasks: startup; WorkingDir: "{app}"

[Run]
Filename: "{app}\Dazzle.exe"; Description: "{cm:LaunchProgram,Dazzle AUTO255}"; Flags: nowait postinstall skipifsilent
