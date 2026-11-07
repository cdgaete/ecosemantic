#define CoreRoot "..\.."
#define AppGuid "73313D0E-AAB0-480A-8C28-E8C6ABA83B89"
#define UninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{" + AppGuid + "}_is1"

#ifdef SignCommand
  #define SetupSuffix ""
#else
  #define SetupSuffix "-unsigned"
#endif

#include "defines.iss"

[Setup]
AppId={{{#AppGuid}}
AppName=EcoSemantic Engine
AppVersion={#AppVersion}
AppVerName=EcoSemantic Engine {#AppVersion}
AppPublisher=Carlos Gaete-Morales
DefaultDirName={userpf}\EcoSemantic Engine
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
UninstallLogMode=append
OutputDir=..\..\dist
OutputBaseFilename=EcoSemantic-Engine-Setup-{#AppVersion}{#SetupSuffix}
LicenseFile={#CoreRoot}\LICENSE
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
#ifdef SignCommand
SignTool=ecosemantic
SignedUninstaller=yes
#endif

[InstallDelete]
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#PayloadDir}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#PayloadDir}\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"
Source: "icon.ico"; DestDir: "{app}"
Source: "{#CoreRoot}\LICENSE"; DestDir: "{app}"
Source: "{#CoreRoot}\NOTICE"; DestDir: "{app}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "EcoSemantic Engine"; ValueData: """{app}\python\pythonw.exe"" -X utf8 -m ecosemantic.tray"; Flags: uninsdeletevalue; Check: EcsRunValueWanted

[Icons]
Name: "{userprograms}\EcoSemantic Engine"; Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 -m ecosemantic.tray"; WorkingDir: "{app}"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 -m ecosemantic.tray --first-run"; Description: "Start EcoSemantic Engine"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{localappdata}\EcoSemantic Engine"

[Code]
#include "folders.iss"

function EcsQuitRefusal(Code: Integer; const Again: String): String;
begin
  if Code = 4 then
    Result := Format('EcoSemantic Engine cannot read its settings, %s. Remove that file or '
      + 'correct it, then run %s again.', [EcsSettingsPath, Again])
  else if Code = 3 then
    Result := Format('EcoSemantic Engine is still running. Quit it from its icon in the '
      + 'notification area, then run %s again.', [Again])
  else
    Result := Format('EcoSemantic Engine answered %d when it was asked to stop. See %s, then '
      + 'run %s again.', [Code, EcsAppFolder + '\logs\tray.log', Again]);
end;

function EcsAskTheTrayToQuit(const Again: String): String;
var
  Code: Integer;
begin
  Result := '';
  if not EcsPreviousInstall then Exit;
  if not Exec(EcsPythonw, '-X utf8 -m ecosemantic.tray --quit', ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, Code) then
  begin
    Result := Format('EcoSemantic Engine could not be asked to stop, %s. Run %s again.',
      [SysErrorMessage(Code), Again]);
    Exit;
  end;
  if Code <> 0 then
    Result := EcsQuitRefusal(Code, Again);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  NeedsRestart := False;
  Result := EcsRefusal;
  if Result = '' then
    Result := EcsAskTheTrayToQuit('Setup');
  if Result <> '' then
    Log(Result);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    EcsWriteSettings;
end;

function GetCustomSetupExitCode: Integer;
begin
  if EcsWriteFailed then
    Result := 9
  else
    Result := 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Refusal: String;
begin
  if CurUninstallStep = usAppMutexCheck then
  begin
    Refusal := EcsAskTheTrayToQuit('the uninstaller');
    if Refusal <> '' then
      RaiseException(Refusal);
  end
  else if CurUninstallStep = usDone then
  begin
    if not UninstallSilent then
      SuppressibleMsgBox('Your two folders and your bridge sign-in are kept. Remove this engine '
        + 'from your account page at https://bridge.ecosemantic.com if you no longer use it.',
        mbInformation, MB_OK, IDOK);
  end;
end;
