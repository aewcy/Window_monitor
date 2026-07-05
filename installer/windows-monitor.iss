#define AppName "GameFrameRateViewer"
#define AppVersion "0.58.1"
#define Publisher "Monitor Demo"
#define SourceRoot ".."

[Setup]
AppId={{7B565767-ACF2-44C5-A85D-43CFEE3C89A3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={commonappdata}\GameFrameRateViewerInstaller
DisableDirPage=yes
DefaultGroupName=GameFrameRateViewer
DisableProgramGroupPage=no
PrivilegesRequired=admin
OutputDir=..\server\static\agent
OutputBaseFilename=WindowsMonitorSetup
SetupIconFile=..\agent\assets\windows-monitor.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\monitor-agent.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceRoot}\server\static\agent\monitor-agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\agent\install-agent.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\agent\updater.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\agent\runner.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\agent\uninstall-agent.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Uninstall GameFrameRateViewer"; Filename: "{uninstallexe}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-agent.ps1"" -Install"; StatusMsg: "Installing and starting GameFrameRateViewer..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-agent.ps1"" -Remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveWindowsMonitorAgent"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
