const
  ECS_APP_FOLDER = 'EcoSemantic Engine';
  ECS_SETTINGS_FILE = 'settings.json';
  ECS_DEFAULT_FOLDER = '\EcoSemantic';
  ECS_PROBE = '.ecosemantic-writable';
  ECS_PYTHONW = '\python\pythonw.exe';
  ECS_RUN_KEY = 'Software\Microsoft\Windows\CurrentVersion\Run';
  ECS_RUN_VALUE = 'EcoSemantic Engine';
  ECS_UNINSTALL_KEY = '{#UninstallKey}';
  ECS_APP_PATH_VALUE = 'Inno Setup: App Path';
  ECS_SETTINGS = '{"databases": "%s", "models": "%s"}';
  ECS_JSON_FROM = '\"';
  ECS_JSON_TO = '\\\"';

var
  EcsDatabasePage: TInputDirWizardPage;
  EcsModelPage: TInputDirWizardPage;
  EcsDatabases: String;
  EcsModels: String;
  EcsDatabasesGiven: Boolean;
  EcsModelsGiven: Boolean;
  EcsKeepSettings: Boolean;
  EcsUpgrading: Boolean;
  EcsWriteFailed: Boolean;

function EcsAppFolder: String;
begin
  Result := ExpandConstant('{localappdata}') + '\' + ECS_APP_FOLDER;
end;

function EcsSettingsPath: String;
begin
  Result := EcsAppFolder + '\' + ECS_SETTINGS_FILE;
end;

function EcsPythonw: String;
begin
  Result := ExpandConstant('{app}') + ECS_PYTHONW;
end;

function EcsPreviousInstall: Boolean;
begin
  Result := FileExists(EcsPythonw);
end;

function EcsRecordedFolder: String;
var
  Folder: String;
begin
  Folder := '';
  if RegQueryStringValue(HKCU, ECS_UNINSTALL_KEY, ECS_APP_PATH_VALUE, Folder) then
    Result := Folder
  else
    Result := '';
end;

function EcsElsewhereRefusal: String;
var
  Folder: String;
begin
  Result := '';
  Folder := EcsRecordedFolder;
  if Folder = '' then Exit;
  if AddBackslash(AnsiLowerCase(ExpandFileName(Folder)))
      = AddBackslash(AnsiLowerCase(ExpandFileName(WizardDirValue))) then
    Exit;
  Result := Format('EcoSemantic Engine is installed in %s. Uninstall it there first, then run '
    + 'Setup again to install it elsewhere.', [Folder]);
end;

function EcsRunValueWanted: Boolean;
begin
  Result := (not EcsUpgrading) or RegValueExists(HKCU, ECS_RUN_KEY, ECS_RUN_VALUE);
end;

function EcsAbsolute(const Folder: String): Boolean;
var
  Letter: String;
begin
  Result := False;
  if Length(Folder) < 3 then Exit;
  if Copy(Folder, 1, 2) = '\\' then
  begin
    Result := Length(Folder) > 3;
    Exit;
  end;
  if Copy(Folder, 2, 2) <> ':\' then Exit;
  Letter := Copy(Folder, 1, 1);
  Result := Pos(Letter, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz') > 0;
end;

function EcsNotAbsoluteRefusal(const What, Folder: String): String;
begin
  if EcsAbsolute(Folder) then
    Result := ''
  else
    Result := Format('The %s folder %s is not an absolute path: it must begin with a drive '
      + 'letter, a colon and a backslash, or with two backslashes and a server name.',
      [What, Folder]);
end;

function EcsEscaped(const Value: String): String;
var
  Index: Integer;
  Mark: Integer;
  Character: String;
begin
  Result := '';
  for Index := 1 to Length(Value) do
  begin
    Character := Copy(Value, Index, 1);
    Mark := Pos(Character, ECS_JSON_FROM);
    if Mark > 0 then
      Result := Result + Copy(ECS_JSON_TO, 2 * Mark - 1, 2)
    else
      Result := Result + Character;
  end;
end;

function EcsLengthRefusal(const What, Folder: String; Budget: Integer): String;
var
  Total: Integer;
begin
  Total := Length(Folder) + 1 + Budget;
  if Total > 259 then
    Result := Format('The %s folder %s is %d characters long, and the longest path EcoSemantic '
      + 'Engine writes beneath it adds %d characters and a backslash, reaching %d: Windows reads at '
      + 'most 259. Choose a shorter folder.',
      [What, Folder, Length(Folder), Budget, Total])
  else
    Result := '';
end;

function EcsUnderRefusal(const What, Folder, Parent: String): String;
var
  Inside: String;
  Root: String;
begin
  Inside := AddBackslash(AnsiLowerCase(Folder));
  Root := AddBackslash(AnsiLowerCase(Parent));
  if Copy(Inside, 1, Length(Root)) = Root then
    Result := Format('The %s folder %s is at or under %s, and uninstalling EcoSemantic Engine '
      + 'removes that folder. Choose a folder outside it.', [What, Folder, Parent])
  else
    Result := '';
end;

function EcsInsideRefusal(const What, Folder: String): String;
begin
  Result := EcsUnderRefusal(What, Folder, ExpandFileName(WizardDirValue));
  if Result = '' then
    Result := EcsUnderRefusal(What, Folder, EcsAppFolder);
end;

function EcsOwnFile(const Found: TFindRec): Boolean;
var
  Lower: String;
begin
  Lower := AnsiLowerCase(Found.Name);
  Result := (Found.Attributes and FILE_ATTRIBUTE_DIRECTORY = 0)
    and ((Lower = 'unins000.exe')
      or (Lower = 'unins000.dat')
      or (Lower = 'unins000.msg')
      or (Lower = 'icon.ico')
      or (Lower = 'license')
      or (Lower = 'notice')
      or (Lower = 'third_party_notices.txt'));
end;

function EcsEmpty(const Folder: String; var Reason: String): Boolean;
var
  Found: TFindRec;
begin
  Result := True;
  Reason := '';
  if not DirExists(Folder) then Exit;
  if not FindFirst(AddBackslash(Folder) + '*', Found) then
  begin
    Result := False;
    Reason := Format('The program folder %s cannot be listed. Choose a folder Windows can list.',
      [Folder]);
    Exit;
  end;
  try
    repeat
      if (Found.Name <> '.') and (Found.Name <> '..') and (not EcsOwnFile(Found)) then
        Result := False;
    until (not Result) or (not FindNext(Found));
  finally
    FindClose(Found);
  end;
end;

function EcsWritableRefusal(const What, Folder: String): String;
var
  Ancestor: String;
  Above: String;
  Probe: String;
begin
  Result := '';
  if FileExists(Folder) then
  begin
    Result := Format('The %s folder %s is a file. Choose a folder.', [What, Folder]);
    Exit;
  end;
  Ancestor := Folder;
  while not DirExists(Ancestor) do
  begin
    Above := ExtractFileDir(Ancestor);
    if Above = Ancestor then
    begin
      Ancestor := '';
      Break;
    end;
    Ancestor := Above;
  end;
  if Ancestor = '' then
  begin
    Result := Format('The %s folder %s cannot be made: no folder above it exists.',
      [What, Folder]);
    Exit;
  end;
  Probe := AddBackslash(Ancestor) + ECS_PROBE;
  if DirExists(Probe) then
    RemoveDir(Probe);
  if not CreateDir(Probe) then
  begin
    Result := Format('The %s folder %s is not writable: %s refused the folder the check makes '
      + 'in it.', [What, Folder, Ancestor]);
    Exit;
  end;
  if not RemoveDir(Probe) then
    Result := Format('The %s folder %s is not writable: the check made %s and could not remove '
      + 'it.', [What, Folder, Probe]);
end;

function EcsInstallRefusal: String;
var
  Folder: String;
  Reason: String;
begin
  Folder := ExpandFileName(WizardDirValue);
  Result := EcsLengthRefusal('program', Folder, {#LongestPath});
  if Result <> '' then Exit;
  if EcsUpgrading then Exit;
  if EcsEmpty(Folder, Reason) then Exit;
  if Reason <> '' then
    Result := Reason
  else
    Result := Format('The program folder %s already holds files, and EcoSemantic Engine is '
      + 'installed into an empty folder or over an earlier installation of itself. Choose an '
      + 'empty folder.', [Folder]);
end;

function EcsFolderRefusal(const What, Given: String; Budget: Integer;
  var Folder: String): String;
begin
  Result := EcsNotAbsoluteRefusal(What, Given);
  if Result <> '' then Exit;
  Folder := ExpandFileName(Given);
  Result := EcsInsideRefusal(What, Folder);
  if Result <> '' then Exit;
  Result := EcsLengthRefusal(What, Folder, Budget);
  if Result <> '' then Exit;
  Result := EcsWritableRefusal(What, Folder);
end;

function EcsRefusal: String;
begin
  EcsUpgrading := EcsPreviousInstall;
  Result := EcsElsewhereRefusal;
  if Result <> '' then Exit;
  if EcsKeepSettings and (EcsDatabasesGiven or EcsModelsGiven) then
  begin
    Result := Format('EcoSemantic Engine is already set up, with its folders in %s. Setup does '
      + 'not move them.', [EcsSettingsPath]);
    Exit;
  end;
  Result := EcsNotAbsoluteRefusal('program', WizardDirValue);
  if Result <> '' then Exit;
  Result := EcsInstallRefusal;
  if Result <> '' then Exit;
  if EcsKeepSettings then Exit;
  Result := EcsFolderRefusal('databases', EcsDatabasePage.Values[0], {#DatabasesBudget},
    EcsDatabases);
  if Result <> '' then Exit;
  Result := EcsFolderRefusal('models', EcsModelPage.Values[0], {#ModelsBudget}, EcsModels);
end;

procedure EcsCannotWrite(const Message: String);
begin
  EcsWriteFailed := True;
  Log(Message);
  if not WizardSilent then
    SuppressibleMsgBox(Message, mbError, MB_OK, IDOK);
end;

procedure EcsWriteSettings;
var
  Lines: TArrayOfString;
  Folder: String;
begin
  if EcsKeepSettings then Exit;
  if not ForceDirectories(EcsDatabases) then
  begin
    EcsCannotWrite(Format('The databases folder %s cannot be made.', [EcsDatabases]));
    Exit;
  end;
  if not ForceDirectories(EcsModels) then
  begin
    EcsCannotWrite(Format('The models folder %s cannot be made.', [EcsModels]));
    Exit;
  end;
  Folder := EcsAppFolder;
  if not ForceDirectories(Folder) then
  begin
    EcsCannotWrite(Format('%s cannot be made, and the two folders are written there.', [Folder]));
    Exit;
  end;
  SetArrayLength(Lines, 1);
  Lines[0] := Format(ECS_SETTINGS, [EcsEscaped(EcsDatabases), EcsEscaped(EcsModels)]);
  if not SaveStringsToUTF8File(EcsSettingsPath, Lines, False) then
    EcsCannotWrite(Format('The two folders cannot be written to %s.', [EcsSettingsPath]));
end;

procedure InitializeWizard;
begin
  EcsDatabases := ExpandConstant('{param:DATABASES|}');
  EcsDatabasesGiven := EcsDatabases <> '';
  if not EcsDatabasesGiven then
    EcsDatabases := ExpandConstant('{%USERPROFILE}') + ECS_DEFAULT_FOLDER + '\databases';
  EcsModels := ExpandConstant('{param:MODELS|}');
  EcsModelsGiven := EcsModels <> '';
  if not EcsModelsGiven then
    EcsModels := ExpandConstant('{%USERPROFILE}') + ECS_DEFAULT_FOLDER + '\models';
  EcsKeepSettings := FileExists(EcsSettingsPath);
  EcsDatabasePage := CreateInputDirPage(wpSelectDir,
    'Databases',
    'Where does EcoSemantic Engine keep its databases?',
    'EcoSemantic Engine serves the background databases from this folder. They are large, and '
      + 'they can be installed again from their sources.',
    False, '');
  EcsDatabasePage.Add('');
  EcsDatabasePage.Values[0] := EcsDatabases;
  EcsModelPage := CreateInputDirPage(EcsDatabasePage.ID,
    'Models',
    'Where does EcoSemantic Engine keep your own work?',
    'EcoSemantic Engine keeps your product systems, the runs they produce and your chat in '
      + 'this folder.',
    False, '');
  EcsModelPage.Add('');
  EcsModelPage.Values[0] := EcsModels;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := EcsKeepSettings and ((PageID = EcsDatabasePage.ID) or (PageID = EcsModelPage.ID));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Refusal: String;
begin
  Result := True;
  if (CurPageID <> EcsDatabasePage.ID) and (CurPageID <> EcsModelPage.ID) then Exit;
  Refusal := EcsRefusal;
  if Refusal = '' then Exit;
  Log(Refusal);
  if not WizardSilent then
    SuppressibleMsgBox(Refusal, mbError, MB_OK, IDOK);
  Result := False;
end;
