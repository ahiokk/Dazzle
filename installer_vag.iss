#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifnexist "dist\DazzleVAG\DazzleVAG.exe"
  #error "EXE VAG не найден. Сначала выполните build_exe.ps1 -Edition vag."
#endif
#ifnexist "assets\dazzle.ico"
  #error "Иконка не найдена: assets\\dazzle.ico"
#endif
#ifnexist "assets\default_settings_vag.json"
  #error "Пресет настроек VAG не найден: assets\\default_settings_vag.json"
#endif

[Setup]
AppId={{691D761D-8182-4900-836B-4F36301B2F9B}
AppName=Dazzle VAG (Windows 10/11)
AppVersion={#AppVersion}
AppPublisher=Dazzle
DefaultDirName={localappdata}\Programs\Dazzle VAG
DefaultGroupName=Dazzle VAG
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Dazzle-VAG-Win10-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\DazzleVAG.exe
SetupIconFile=assets\dazzle.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "Дополнительно:"
Name: "startup"; Description: "Запускать вместе с Windows"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\DazzleVAG\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\default_settings_vag.json"; DestDir: "{userappdata}\Dazzle"; DestName: "settings.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\Dazzle VAG"; Filename: "{app}\DazzleVAG.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Dazzle VAG"; Filename: "{app}\DazzleVAG.exe"; Tasks: desktopicon; WorkingDir: "{app}"
Name: "{userstartup}\Dazzle"; Filename: "{app}\DazzleVAG.exe"; Tasks: startup; WorkingDir: "{app}"

[Run]
Filename: "{app}\DazzleVAG.exe"; Description: "{cm:LaunchProgram,Dazzle VAG}"; Flags: nowait postinstall skipifsilent
