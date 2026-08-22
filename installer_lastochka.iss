#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

; Редакция Lastochka (магазин на Windows 7).
; AppId и имя exe (DazzleWin7.exe) намеренно прежние: по ним обновляются
; уже установленные копии. Меняются только видимые названия.

#ifnexist "dist\DazzleWin7\DazzleWin7.exe"
  #error "EXE Lastochka не найден. Сначала выполните build_exe_lastochka.ps1."
#endif
#ifnexist "assets\dazzle.ico"
  #error "Иконка не найдена: assets\\dazzle.ico"
#endif
#ifnexist "assets\default_settings_lastochka.json"
  #error "Пресет настроек Lastochka не найден: assets\\default_settings_lastochka.json"
#endif

[Setup]
AppId={{C9B90829-46DA-4C34-8AA0-1A6E04B7C5A8}
AppName=Dazzle Lastochka (Windows 7)
AppVersion={#AppVersion}
AppPublisher=Dazzle
DefaultDirName={localappdata}\Programs\Dazzle Lastochka
DefaultGroupName=Dazzle Lastochka
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Dazzle-Lastochka-Win7-Setup-{#AppVersion}
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

[InstallDelete]
; Ярлыки прошлых версий назывались «Dazzle Win7» — убираем, чтобы не двоились.
Type: files; Name: "{autoprograms}\Dazzle Win7.lnk"
Type: files; Name: "{autodesktop}\Dazzle Win7.lnk"
Type: files; Name: "{userstartup}\Dazzle Win7.lnk"

[Files]
Source: "dist\DazzleWin7\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\default_settings_lastochka.json"; DestDir: "{userappdata}\Dazzle"; DestName: "settings.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\Dazzle Lastochka"; Filename: "{app}\DazzleWin7.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Dazzle Lastochka"; Filename: "{app}\DazzleWin7.exe"; Tasks: desktopicon; WorkingDir: "{app}"
Name: "{userstartup}\Dazzle"; Filename: "{app}\DazzleWin7.exe"; Tasks: startup; WorkingDir: "{app}"

[Run]
Filename: "{app}\DazzleWin7.exe"; Description: "{cm:LaunchProgram,Dazzle Lastochka}"; Flags: nowait postinstall skipifsilent
