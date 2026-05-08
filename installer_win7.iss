#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifnexist "dist\DazzleWin7\DazzleWin7.exe"
  #error "EXE Win7 не найден. Сначала выполните build_exe_win7.ps1."
#endif
#ifnexist "assets\dazzle.ico"
  #error "Иконка не найдена: assets\\dazzle.ico"
#endif
#ifnexist "assets\default_settings.json"
  #error "Пресет настроек не найден: assets\\default_settings.json"
#endif

[Setup]
AppId={{C9B90829-46DA-4C34-8AA0-1A6E04B7C5A8}
AppName=Dazzle Win7
AppVersion={#AppVersion}
AppPublisher=Dazzle
DefaultDirName={localappdata}\Programs\Dazzle Win7
DefaultGroupName=Dazzle Win7
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Dazzle-Win7-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\DazzleWin7.exe
SetupIconFile=assets\dazzle.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "Дополнительно:"
Name: "startup"; Description: "Запускать вместе с Windows"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\DazzleWin7\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\default_settings.json"; DestDir: "{userappdata}\Dazzle"; DestName: "settings.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\Dazzle Win7"; Filename: "{app}\DazzleWin7.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Dazzle Win7"; Filename: "{app}\DazzleWin7.exe"; Tasks: desktopicon; WorkingDir: "{app}"
Name: "{userstartup}\Dazzle Win7"; Filename: "{app}\DazzleWin7.exe"; Tasks: startup; WorkingDir: "{app}"

[Run]
Filename: "{app}\DazzleWin7.exe"; Description: "{cm:LaunchProgram,Dazzle Win7}"; Flags: nowait postinstall skipifsilent

