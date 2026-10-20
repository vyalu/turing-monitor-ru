; Установщик Turing Monitor RU (Inno Setup 6)
; Сборка: iscc /DAppVersion=1.0.1 /DSourceDir=..\dist-dir\TuringMonitorRU packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist-dir\TuringMonitorRU"
#endif

#define AppName "Turing Monitor RU"
#define AppExe "TuringMonitorRU.exe"
#define TaskName "TuringMonitorRU"

[Setup]
AppId={{6F3D2C1E-8A4B-4E8C-9B1A-7C2D5E9F0A31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=vyalu
AppPublisherURL=https://github.com/vyalu/turing-monitor-ru
AppSupportURL=https://github.com/vyalu/turing-monitor-ru/issues
AppUpdatesURL=https://github.com/vyalu/turing-monitor-ru/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=TuringMonitorRU-Setup-{#AppVersion}
SetupIconFile=..\src\turmon\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Установщик {#AppName}

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "pawnio"; Description: "Установить драйвер PawnIO (нужен для температуры и частот процессора)"; GroupDescription: "Датчики:"; Check: IsAdminInstallMode and not PawnIOInstalled
Name: "autostart"; Description: "Запускать вместе с Windows (с правами администратора — работают все датчики)"; GroupDescription: "Запуск:"; Check: IsAdminInstallMode

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\lhm\PawnIO_setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist; Tasks: pawnio

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\PawnIO_setup.exe"; Parameters: "-install -silent"; Flags: runhidden waituntilterminated skipifdoesntexist; Tasks: pawnio; StatusMsg: "Установка драйвера PawnIO…"
; задача планировщика: запуск при входе в систему с наивысшими правами, без запроса UAC
Filename: "{sys}\schtasks.exe"; \
  Parameters: "/Create /TN ""{#TaskName}"" /TR ""\""{app}\{#AppExe}\"" --minimized"" /SC ONLOGON /RL HIGHEST /DELAY 0000:15 /F"; \
  Flags: runhidden waituntilterminated; Tasks: autostart; StatusMsg: "Настройка автозапуска…"
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""{#TaskName}"" /F"; Flags: runhidden; RunOnceId: "DelTask"
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v TuringMonitorRU /f"; Flags: runhidden; RunOnceId: "DelRunKey"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function PawnIOInstalled(): Boolean;
begin
  Result := RegKeyExists(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO') or
            RegKeyExists(HKLM32, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO');
end;

procedure StopRunningApp();
var
  Code: Integer;
begin
  { программа держит COM-порт и файлы в папке — закрываем её перед копированием }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExe} /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(800);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\TuringMonitorRU');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Удалить также настройки и ваши темы?' + #13#10 + DataDir, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
