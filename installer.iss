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
AppName=Dazzle
AppVersion={#AppVersion}
AppPublisher=Dazzle
DefaultDirName={localappdata}\Programs\Dazzle
DefaultGroupName=Dazzle
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Dazzle-Setup-{#AppVersion}
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

[Files]
Source: "dist\Dazzle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\default_settings.json"; DestDir: "{userappdata}\Dazzle"; DestName: "settings.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\Dazzle"; Filename: "{app}\Dazzle.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Dazzle"; Filename: "{app}\Dazzle.exe"; Tasks: desktopicon; WorkingDir: "{app}"
Name: "{userstartup}\Dazzle"; Filename: "{app}\Dazzle.exe"; Tasks: startup; WorkingDir: "{app}"

[Run]
Filename: "{app}\Dazzle.exe"; Description: "{cm:LaunchProgram,Dazzle}"; Flags: nowait postinstall skipifsilent
