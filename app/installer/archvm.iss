; Inno Setup script for ArchVM Manager.
;
;   iscc /DAppVersion=2.1.0 app\installer\archvm.iss
;
; Expects the PyInstaller onedir bundle at app\dist\ArchVM\.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName     "ArchVM Manager"
#define AppExeName  "ArchVM.exe"
#define AppPublisher "nikhlgoel"
#define AppURL      "https://github.com/nikhlgoel/ArchVM-manager"

[Setup]
; Never reuse this GUID for another product - it is how Windows recognises
; an existing install and offers to upgrade rather than duplicate it.
AppId={{7B2F4E19-6C3A-4D58-9E01-2A7C5F8B3D46}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

DefaultDirName={autopf}\ArchVM
DefaultGroupName={#AppName}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile=..\..\LICENSE

; The app itself does not need administrator rights - the setup wizard elevates
; only the individual fixes that require it. So offer a per-user install too,
; which needs no UAC prompt at all.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

OutputDir=..\..\release
OutputBaseFilename=ArchVM-{#AppVersion}-windows-x64-setup
SetupIconFile=..\assets\archvm.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
  GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\ArchVM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\README.md";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE";    DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\docs\vm-guide.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"
Name: "{group}\VM guide";          Filename: "{app}\docs\vm-guide.md"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller writes __pycache__ next to the bundle at runtime; without this the
; install directory is left behind after uninstalling.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
{ Settings live in %APPDATA%\ArchVM and the VM disks live wherever the user
  pointed ARCHVM_ROOT. Deleting either on uninstall would destroy a 100 GB VM
  and the configuration behind it, so we ask rather than assume - and default
  to keeping. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    ConfigDir := ExpandConstant('{userappdata}\ArchVM');
    if DirExists(ConfigDir) then
      if MsgBox('Also remove your ArchVM settings?' + #13#10#13#10 +
                ConfigDir + #13#10#13#10 +
                'Your virtual machine disks and ISOs are stored separately and ' +
                'will NOT be touched either way.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(ConfigDir, True, True, True);
  end;
end;
