; Installateur Windows 11 — Centre de contrôle & Moniteur 480x320 (WinUI 3 / .NET 10 self-contained)
#define MyAppName "Centre de contrôle"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "yoyo1306"
#define MyAppURL "https://github.com/yoyo1306/Centre"
#define MyAppExeName "CentreControle.exe"
#define MyPanelExeName "Moniteur.exe"

[Setup]
AppId={{8F93A4C2-3E5B-4D17-9A61-2C4B7E10F82A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\Centre de contrôle
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=CentreControle-Setup-{#MyAppVersion}
SetupIconFile=..\ico.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern dynamic
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
MinVersion=10.0.19041

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "autostart"; Description: "Lancer le Moniteur 480×320 automatiquement au démarrage de Windows"; GroupDescription: "Démarrage :"

[Dirs]
Name: "{commonappdata}\CentreControle"; Permissions: users-modify

[Files]
; Fichiers publiés (CentreControle.exe + Moniteur.exe + runtime .NET 10 & WinUI 3 partagés)
Source: "..\publish\*"; DestDir: "{app}"; Excludes: "config.ini,centre.ini"; Flags: ignoreversion recursesubdirs createallsubdirs
; Préserve config.ini lors d'une mise à jour
Source: "..\publish\config.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist
; Police digitale installée dans Windows pour un rendu garanti sur PC vierge
Source: "..\assets\dash-digital.ttf"; DestDir: "{autofonts}"; FontInstall: "Dash Digital-7"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\ico.ico"
Name: "{group}\Moniteur 480×320"; Filename: "{app}\{#MyPanelExeName}"; IconFilename: "{app}\ico.ico"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\ico.ico"; Tasks: desktopicon

[Run]
; Installe PawnIO silencieusement si absent sur le PC (nécessaire pour la température CPU Ryzen/Intel)
Filename: "{app}\libs\PawnIO_setup.exe"; Parameters: "-install -silent"; StatusMsg: "Installation du pilote capteurs CPU (PawnIO)…"; Flags: runhidden waituntilterminated; Check: PawnIoNotInstalled
; Crée la tâche planifiée SensorPanel si cochée
Filename: "{sys}\schtasks.exe"; Parameters: "/Create /F /TN ""SensorPanel"" /SC ONLOGON /RL HIGHEST /IT /TR ""\""{app}\{#MyPanelExeName}\"""""; StatusMsg: "Configuration du démarrage automatique…"; Flags: runhidden waituntilterminated; Tasks: autostart
; Lancement direct du Centre à la fin (en utilisateur standard non élevé)
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyPanelExeName}"; Flags: runhidden; RunOnceId: "KillMoniteur"
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillCentre"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN ""SensorPanel"""; Flags: runhidden; RunOnceId: "DeleteStartupTask"

[Code]
function PawnIoNotInstalled: Boolean;
var
  InstallLoc: String;
begin
  Result := True;
  if RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO', 'InstallLocation', InstallLoc) then
  begin
    if FileExists(AddBackslash(InstallLoc) + 'PawnIOLib.dll') then
      Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im {#MyPanelExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
