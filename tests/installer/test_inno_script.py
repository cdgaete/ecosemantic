"""What the Inno Setup installer does, read from its two scripts on any host: only Windows
compiles them, so every rule the brief states is held here as text the compiler will read."""

from __future__ import annotations

import re
from pathlib import Path

from ecosemantic.tray.home import TraySettings

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "installer" / "windows"
SETUP = WINDOWS / "EcoSemanticEngine.iss"
FOLDERS = WINDOWS / "folders.iss"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
INSTALL = r"C:\Users\José Muñoz Fernández-Larraín\AppData\Local\Programs\EcoSemantic Engine"
TRAY = '"%s\\python\\pythonw.exe" -X utf8 -m ecosemantic.tray'


def setup_script() -> str:
    return SETUP.read_text(encoding="utf-8")


def folders_script() -> str:
    return FOLDERS.read_text(encoding="utf-8")


def spelled(script: str) -> str:
    """The script's Pascal string literals joined across their `' + '` continuations, so a sentence
    split over two lines reads as the one text the compiler builds."""
    return re.sub(r"'\s*\+\s*'", "", script)


def everything() -> str:
    return spelled(setup_script() + folders_script())


def sections(script: str) -> dict[str, list[str]]:
    """The script's sections, each as its entry lines, keyed by the name inside the brackets."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current = found.setdefault(line[1:-1], [])
        elif current is not None and line and not line.startswith(";"):
            current.append(line)
    return found


def directives(script: str) -> dict[str, str]:
    """The [Setup] section's `Directive=value` lines, keyed by the directive's name."""
    named: dict[str, str] = {}
    for line in sections(script)["Setup"]:
        name, _, value = line.partition("=")
        named[name.strip()] = value.strip()
    return named


def inno_quoted(value: str) -> str:
    """How a section parameter spells a value Inno reads back whole: quoted, its own quotes
    doubled."""
    return '"' + value.replace('"', '""') + '"'


def unquoted(value: str) -> str:
    """A section parameter's value as Inno reads it, a doubled quote inside standing for one."""
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value


def parameters(entry: str) -> dict[str, str]:
    """One section entry's named parameters, each value as the script spells it."""
    named: dict[str, str] = {}
    for match in re.finditer(r"(\w+):\s*([^;]*?)\s*(?:;|$)", entry):
        named[match.group(1)] = match.group(2)
    return named


def entries(script: str, section: str) -> list[dict[str, str]]:
    return [parameters(line) for line in sections(script).get(section, [])]


def run_value() -> dict[str, str]:
    """The Run entry this product writes, which starts the tray at every login."""
    for entry in entries(setup_script(), "Registry"):
        if unquoted(entry["ValueName"]) == "EcoSemantic Engine":
            return entry
    raise AssertionError("the script writes no Run value named EcoSemantic Engine")


def functions(script: str) -> dict[str, str]:
    """Each Pascal routine, keyed by its name, from its `function` or `procedure` line to the
    unindented `end;` that closes it."""
    lines = spelled(script).splitlines()
    found: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = re.match(r"(?:function|procedure)\s+(\w+)", line)
        if not match:
            continue
        closing = next(where for where in range(index, len(lines)) if lines[where] == "end;")
        found[match.group(1)] = "\n".join(lines[index : closing + 1])
    return found


def pascal_string(script: str, name: str) -> str:
    """The value of one Pascal string constant, with its doubled apostrophes read as one."""
    match = re.search(rf"^\s*{name}\s*=\s*'(.*)'\s*;", script, re.MULTILINE)
    assert match, f"the scripts hold no Pascal constant {name}"
    return match.group(1).replace("''", "'")


def test_the_installer_never_asks_for_administrator_rights_or_writes_hklm() -> None:
    setup = directives(setup_script())
    assert setup["PrivilegesRequired"] == "lowest"
    assert "PrivilegesRequiredOverridesAllowed" not in setup
    assert setup["DefaultDirName"] == r"{userpf}\EcoSemantic Engine"
    text = everything()
    assert "HKLM" not in text
    for machine_wide in ("Program Files", "{commonpf}", "{pf}", "{autopf}", "{commonprograms}"):
        assert machine_wide not in text, machine_wide
    assert {unquoted(entry["Root"]) for entry in entries(setup_script(), "Registry")} == {"HKCU"}


def test_the_run_command_fits_the_run_key_for_a_long_user_name() -> None:
    written = run_value()
    assert unquoted(written["Subkey"]) == RUN_KEY
    assert written["ValueData"] == inno_quoted(TRAY % "{app}"), written["ValueData"]
    command = unquoted(written["ValueData"]).replace("{app}", INSTALL)
    assert command == TRAY % INSTALL
    assert len(command) <= 260, len(command)


def test_the_run_value_the_shortcut_and_the_run_entry_all_start_the_tray() -> None:
    shortcut = entries(setup_script(), "Icons")[0]
    assert unquoted(shortcut["Name"]) == r"{userprograms}\EcoSemantic Engine"
    assert unquoted(shortcut["Filename"]) == r"{app}\python\pythonw.exe"
    assert unquoted(shortcut["Parameters"]) == "-X utf8 -m ecosemantic.tray"
    started = entries(setup_script(), "Run")[0]
    assert unquoted(started["Filename"]) == r"{app}\python\pythonw.exe"
    assert unquoted(started["Parameters"]) == "-X utf8 -m ecosemantic.tray --first-run"
    assert set(unquoted(started["Flags"]).split()) == {"postinstall", "nowait", "skipifsilent"}


def test_every_folder_is_held_to_its_length_budget() -> None:
    folders = folders_script()
    assert "Total := Length(Folder) + 1 + Budget;" in folders, folders
    assert "if Total > 259 then" in folders, folders
    assert folders.count("{#LongestPath}") == 1
    assert folders.count("{#DatabasesBudget}") == 1
    assert folders.count("{#ModelsBudget}") == 1
    assert re.search(r"EcsLengthRefusal\('program', Folder, \{#LongestPath\}\)", folders), folders
    assert re.search(
        r"EcsFolderRefusal\('databases', EcsDatabasePage.Values\[0\], \{#DatabasesBudget\}",
        folders,
    ), folders
    assert re.search(
        r"EcsFolderRefusal\('models', EcsModelPage.Values\[0\], \{#ModelsBudget\}", folders
    ), folders
    refusal = functions(setup_script())["PrepareToInstall"]
    assert "EcsRefusal" in refusal and "Log(" in refusal, refusal


def test_the_folder_checks_run_before_the_tray_is_stopped() -> None:
    refusal = functions(setup_script())["PrepareToInstall"]
    assert refusal.index("EcsRefusal") < refusal.index("EcsAskTheTrayToQuit"), refusal


def test_the_payload_its_notices_and_the_licence_are_what_it_copies() -> None:
    copied = [
        (
            unquoted(entry["Source"]),
            unquoted(entry["DestDir"]),
            unquoted(entry.get("Flags", "")).split(),
        )
        for entry in entries(setup_script(), "Files")
    ]
    payload = (
        r"{#PayloadDir}\python\*",
        r"{app}\python",
        ["recursesubdirs", "createallsubdirs", "ignoreversion"],
    )
    assert copied[0] == payload, copied[0]
    assert {destination for _, destination, _ in copied} == {r"{app}\python", r"{app}"}
    assert {source.rsplit("\\", 1)[-1] for source, _, _ in copied} == {
        "*",
        "THIRD_PARTY_NOTICES.txt",
        "icon.ico",
        "LICENSE",
        "NOTICE",
    }


def test_an_upgrade_replaces_the_payload_it_finds() -> None:
    assert directives(setup_script())["UninstallLogMode"] == "append"
    deleted = [unquoted(entry["Name"]) for entry in entries(setup_script(), "InstallDelete")]
    assert deleted == [r"{app}\python"], deleted


def test_the_run_value_is_written_only_when_the_person_kept_it() -> None:
    written = run_value()
    assert unquoted(written["Check"]) == "EcsRunValueWanted"
    folders = folders_script()
    assert pascal_string(folders, "ECS_RUN_KEY") == unquoted(written["Subkey"])
    assert pascal_string(folders, "ECS_RUN_VALUE") == unquoted(written["ValueName"])
    wanted = functions(folders)["EcsRunValueWanted"]
    assert "not EcsUpgrading" in wanted, wanted
    assert "RegValueExists(HKCU, ECS_RUN_KEY, ECS_RUN_VALUE)" in wanted, wanted
    refusal = functions(folders)["EcsRefusal"]
    assert "EcsUpgrading := EcsPreviousInstall;" in refusal, refusal
    assert everything().count("EcsUpgrading := ") == 1, "EcsUpgrading is recorded once"


def test_the_run_value_and_the_app_s_folder_go_with_the_uninstall_and_the_data_folders_stay() -> (
    None
):
    assert "uninsdeletevalue" in unquoted(run_value()["Flags"]).split()
    deleted = [unquoted(entry["Name"]) for entry in entries(setup_script(), "UninstallDelete")]
    assert deleted == [r"{app}", r"{localappdata}\EcoSemantic Engine"]
    assert {unquoted(entry["Type"]) for entry in entries(setup_script(), "UninstallDelete")} == {
        "filesandordirs"
    }
    assert "UninstallRun" not in sections(setup_script())
    assert "USERPROFILE" not in "".join(deleted)


def test_the_kept_message_waits_for_the_uninstall_to_finish() -> None:
    steps = functions(setup_script())["CurUninstallStepChanged"]
    kept = steps.index("Your two folders and your bridge sign-in are kept")
    assert "usDone" in steps[:kept], steps
    assert "usPostUninstall" not in steps, steps
    assert "not UninstallSilent" in steps, steps


def test_signing_is_on_only_with_a_sign_command() -> None:
    setup = setup_script()
    blocks = re.findall(r"#ifdef SignCommand\n(.*?)#endif", setup, re.DOTALL)
    assert len(blocks) == 2, blocks
    signed = [block for block in blocks if "SignTool" in block]
    unsigned = [block for block in blocks if "SetupSuffix" in block]
    assert len(signed) == 1 and len(unsigned) == 1, blocks
    assert "SignTool=ecosemantic" in signed[0]
    assert "SignedUninstaller=yes" in signed[0]
    signed_half, _, plain_half = unsigned[0].partition("#else")
    assert '#define SetupSuffix ""' in signed_half, unsigned[0]
    assert '#define SetupSuffix "-unsigned"' in plain_half, unsigned[0]
    assert "OutputBaseFilename=EcoSemantic-Engine-Setup-{#AppVersion}{#SetupSuffix}" in setup, setup


def test_the_quit_codes_name_a_running_tray_and_a_settings_file_it_cannot_read() -> None:
    script = setup_script()
    asking = functions(script)["EcsAskTheTrayToQuit"]
    assert "--quit" in asking, asking
    assert "if Code <> 0 then" in asking, asking
    assert "if not EcsPreviousInstall then Exit;" in asking, asking
    code = functions(script)["EcsQuitRefusal"]
    settings_half, _, running_half = code.partition("else if Code = 3")
    assert "Code = 4" in settings_half, code
    assert "EcoSemantic Engine cannot read its settings, %s." in settings_half, code
    assert "EcsSettingsPath" in settings_half, code
    assert "EcoSemantic Engine is still running." in running_half, code
    assert "cannot read its settings" not in running_half, code
    assert "answered %d" in running_half, code
    assert "tray.log" in running_half, code


def test_the_install_and_the_uninstall_say_which_one_to_run_again() -> None:
    script = setup_script()
    asking = functions(script)["EcsAskTheTrayToQuit"]
    assert "const Again: String" in asking, asking
    assert "EcsAskTheTrayToQuit('Setup')" in functions(script)["PrepareToInstall"]
    steps = functions(script)["CurUninstallStepChanged"]
    assert "EcsAskTheTrayToQuit('the uninstaller')" in steps, steps
    assert "RaiseException(Refusal)" in steps, steps
    assert "usAppMutexCheck" in steps, steps
    assert "InitializeUninstall" not in script, "the quit runs after the person confirms"


def test_a_data_folder_a_folder_the_uninstall_removes_is_never_accepted() -> None:
    folders = folders_script()
    inside = functions(folders)["EcsInsideRefusal"]
    assert "EcsUnderRefusal(What, Folder, ExpandFileName(WizardDirValue))" in inside, inside
    assert "EcsUnderRefusal(What, Folder, EcsAppFolder)" in inside, inside
    under = functions(folders)["EcsUnderRefusal"]
    assert "AnsiLowerCase(Folder)" in under, under
    assert "AnsiLowerCase(Parent)" in under, under
    assert "LowerCase(Folder)" not in under.replace("AnsiLowerCase(Folder)", ""), under
    assert "The %s folder %s is at or under %s" in under, under
    for what in ("databases", "models"):
        assert f"EcsFolderRefusal('{what}', " in folders, what


def test_a_program_folder_that_already_holds_files_is_refused() -> None:
    folders = folders_script()
    install = functions(folders)["EcsInstallRefusal"]
    assert "if EcsUpgrading then Exit;" in install, install
    assert "if EcsEmpty(Folder, Reason) then Exit;" in install, install
    assert "already holds files" in install, install
    empty = functions(folders)["EcsEmpty"]
    assert "if not FindFirst(AddBackslash(Folder) + '*', Found) then" in empty, empty
    failed = empty[empty.index("if not FindFirst") : empty.index("try")]
    assert "Result := False;" in failed, failed
    assert "cannot be listed" in failed, failed
    assert "SysErrorMessage" not in empty, empty
    assert "if not DirExists(Folder) then Exit;" in empty, empty
    repeated = empty[empty.index("repeat") : empty.index("until")]
    assert "Result := False;" in repeated, repeated
    assert "Result := True;" not in repeated, repeated
    assert "FindClose(Found)" in empty, empty


def test_a_folder_that_holds_only_what_this_installer_leaves_is_empty() -> None:
    folders = folders_script()
    own = functions(folders)["EcsOwnFile"]
    names = set(re.findall(r"Lower = '([^']+)'", own))
    assert names == {
        "unins000.exe",
        "unins000.dat",
        "unins000.msg",
        "icon.ico",
        "license",
        "notice",
        "third_party_notices.txt",
    }, names
    assert "Found.Attributes and FILE_ATTRIBUTE_DIRECTORY = 0" in own, own

    def ours(name: str, directory: bool) -> bool:
        return not directory and name.lower() in names

    empty = functions(folders)["EcsEmpty"]
    condition = re.search(r"until (.+);", empty).group(1)
    assert condition.startswith("(not Result) or"), condition
    assert "or (not FindNext(Found))" in condition, condition
    assert "(not EcsOwnFile(Found))" in empty, empty

    def holds_nothing(listing: list[tuple[str, bool]]) -> bool:
        """The loop the script runs, each entry paired with whether it is a folder: it stops at the
        first name that is not the installer's own, and the folder held nothing of the person's when
        it ran out of names first."""
        for name, directory in listing:
            if name not in (".", "..") and not ours(name, directory):
                return False
        return True

    assert holds_nothing([(".", True), ("..", True)]), "a fresh folder holds nothing"
    assert not holds_nothing([(".", True), ("..", True), ("unrelated.docx", False)]), "a file"
    assert holds_nothing(
        [
            (".", True),
            ("..", True),
            ("unins000.exe", False),
            ("unins000.dat", False),
            ("unins000.msg", False),
            ("icon.ico", False),
            ("LICENSE", False),
            ("NOTICE", False),
            ("THIRD_PARTY_NOTICES.txt", False),
        ]
    ), "only this installer's own files are there"
    assert not holds_nothing([(".", True), ("..", True), ("unins000.dat.bak", False)]), "a copy"
    assert not holds_nothing([(".", True), ("..", True), ("LICENSE", True)]), "a folder of ours"
    assert not holds_nothing(
        [(".", True), ("..", True), ("THIRD_PARTY_NOTICES.txt", False), ("unrelated.docx", False)]
    )


def test_a_folder_that_is_not_absolute_is_refused() -> None:
    folders = folders_script()
    absolute = functions(folders)["EcsAbsolute"]
    assert "Copy(Folder, 1, 2) = '\\\\'" in absolute, absolute
    assert "Copy(Folder, 2, 2) <> ':\\'" in absolute, absolute
    refusal = functions(folders)["EcsNotAbsoluteRefusal"]
    assert "is not an absolute path" in refusal, refusal
    assert "EcsNotAbsoluteRefusal('program', WizardDirValue)" in folders
    folder = functions(folders)["EcsFolderRefusal"]
    assert "EcsNotAbsoluteRefusal(What, Given)" in folder, folder
    assert "Folder := ExpandFileName(Given);" in folder, folder


def test_an_install_in_another_folder_is_refused_and_the_old_one_is_quit() -> None:
    setup = setup_script()
    assert directives(setup)["AppId"] == "{{{#AppGuid}}"
    guid = re.search(r'#define AppGuid "([^"]+)"', setup).group(1)
    assert re.fullmatch(r"[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}", guid), guid
    folders = folders_script()
    defined = re.search(r'#define UninstallKey "(.*?)" \+ AppGuid \+ "(.*?)"', setup)
    assert defined, "the uninstall key is built from the AppId's GUID"
    assert pascal_string(folders, "ECS_UNINSTALL_KEY") == "{#UninstallKey}"
    key = defined.group(1) + guid + defined.group(2)
    assert key == rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{{{guid}}}_is1"
    assert pascal_string(folders, "ECS_APP_PATH_VALUE") == "Inno Setup: App Path"
    recorded = functions(folders)["EcsRecordedFolder"]
    assert "RegQueryStringValue(HKCU, ECS_UNINSTALL_KEY, ECS_APP_PATH_VALUE, Folder)" in recorded
    refusal = functions(folders)["EcsElsewhereRefusal"]
    assert "AddBackslash(AnsiLowerCase(ExpandFileName(Folder)))" in refusal, refusal
    assert "= AddBackslash(AnsiLowerCase(ExpandFileName(WizardDirValue)))" in refusal, refusal
    assert (
        "EcoSemantic Engine is installed in %s. Uninstall it there first, then run Setup again to "
        "install it elsewhere." in refusal
    ), refusal
    assert "Result := EcsElsewhereRefusal;" in functions(folders)["EcsRefusal"]
    asking = functions(setup)["EcsAskTheTrayToQuit"]
    assert "if not EcsPreviousInstall then Exit;" in asking, asking
    assert "Exec(EcsPythonw," in asking, asking
    assert "EcsTrayPythonw" not in everything(), "the quit names one path for the tray"
    assert [name for name in functions(folders) if "Pythonw" in name] == ["EcsPythonw"], sorted(
        functions(folders)
    )


def test_the_writable_probe_stops_when_no_folder_above_exists() -> None:
    writable = functions(folders_script())["EcsWritableRefusal"]
    assert "while not DirExists(Ancestor) do" in writable, writable
    assert "if Above = Ancestor then" in writable, writable
    assert "Ancestor := '';" in writable, writable
    assert "no folder above it exists" in writable, writable


def test_a_failed_settings_write_exits_non_zero() -> None:
    folders = folders_script()
    writer = functions(folders)["EcsWriteSettings"]
    assert "RaiseException" not in writer, writer
    assert (
        "if not SaveStringsToUTF8File(EcsSettingsPath, Lines, False) then\n    EcsCannotWrite("
    ) in writer, writer
    failed = functions(folders)["EcsCannotWrite"]
    assert "EcsWriteFailed := True;" in failed, failed
    assert "Log(Message);" in failed, failed
    assert "if not WizardSilent then" in failed, failed
    assert "SuppressibleMsgBox(Message, mbError, MB_OK, IDOK);" in failed, failed
    exit_code = functions(setup_script())["GetCustomSetupExitCode"]
    assert "if EcsWriteFailed then" in exit_code, exit_code
    assert "Result := 9" in exit_code, exit_code


def test_a_fresh_install_makes_both_data_folders() -> None:
    folders = folders_script()
    writer = functions(folders)["EcsWriteSettings"]
    assert "if not ForceDirectories(EcsDatabases) then" in writer, writer
    assert "if not ForceDirectories(EcsModels) then" in writer, writer
    assert writer.count("EcsCannotWrite(") == 4, writer
    guard = writer.index("if EcsKeepSettings then Exit;")
    assert guard < writer.index("ForceDirectories(EcsDatabases)"), writer
    assert guard < writer.index("ForceDirectories(EcsModels)"), writer
    assert guard < writer.index("SaveStringsToUTF8File"), writer
    assert "The databases folder %s cannot be made." in writer, writer
    assert "The models folder %s cannot be made." in writer, writer
    for made in ("{app}", r"{localappdata}\EcoSemantic Engine"):
        deleted = [unquoted(entry["Name"]) for entry in entries(setup_script(), "UninstallDelete")]
        assert made in deleted, deleted


def test_the_settings_file_escapes_backslashes_and_quotes(tmp_path: Path) -> None:
    folders = folders_script()
    assert "SaveStringsToUTF8File(EcsSettingsPath, Lines, False)" in folders, folders
    replaced = pascal_string(folders, "ECS_JSON_FROM")
    replacements = pascal_string(folders, "ECS_JSON_TO")
    document = pascal_string(folders, "ECS_SETTINGS")
    assert len(replacements) == 2 * len(replaced), (replaced, replacements)
    table = {found: replacements[2 * index : 2 * index + 2] for index, found in enumerate(replaced)}
    assert table == {"\\": "\\\\", '"': '\\"'}, table

    def escaped(value: str) -> str:
        return "".join(table.get(letter, letter) for letter in value)

    databases = 'C:\\Users\\José "Pepe" Muñoz\\EcoSemantic\\databases'
    models = 'C:\\Users\\José "Pepe" Muñoz\\EcoSemantic\\models'
    written = tmp_path / "settings.json"
    saved = "\ufeff" + document % (escaped(databases), escaped(models)) + "\r\n"
    written.write_bytes(saved.encode("utf-8"))
    assert TraySettings.read(written) == TraySettings(
        databases=Path(databases), models=Path(models)
    )


def test_the_settings_an_install_already_wrote_are_kept_and_a_folder_it_is_given_is_refused() -> (
    None
):
    folders = folders_script()
    assert "ECS_DEFAULT_FOLDER = '\\EcoSemantic';" in folders, folders
    assert folders.count("CreateInputDirPage(") == 2, folders
    for given in ("Databases", "Models"):
        assert f"'{given}'," in folders, given
    for folder in ("databases", "models"):
        assert f"ExpandConstant('{{%USERPROFILE}}') + ECS_DEFAULT_FOLDER + '\\{folder}'" in folders
    assert "ExpandConstant('{param:DATABASES|}')" in folders
    assert "ExpandConstant('{param:MODELS|}')" in folders
    assert "EcsKeepSettings := FileExists(EcsSettingsPath);" in folders, folders
    refusal = functions(folders)["EcsRefusal"]
    assert "if EcsKeepSettings and (EcsDatabasesGiven or EcsModelsGiven) then" in refusal, refusal
    assert (
        "EcoSemantic Engine is already set up, with its folders in %s. Setup does not move them."
        in refusal
    ), refusal
    writer = functions(folders)["EcsWriteSettings"]
    assert writer.index("if EcsKeepSettings then Exit;") < writer.index("SaveStringsToUTF8File")
    assert folders.count("SaveStringsToUTF8File") == 1
    skipping = functions(folders)["ShouldSkipPage"]
    assert "EcsKeepSettings" in skipping and "EcsDatabasePage.ID" in skipping, skipping
    assert "EcsModelPage.ID" in skipping, skipping
