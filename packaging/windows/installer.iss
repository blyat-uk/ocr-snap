; OCR Snap's Windows installer (Inno Setup 6). Built by packaging/build.py:
;   ISCC /DAppVersion=5.1.0 /DSourceDir=<tree> /DOutputDir=<dist>
;        /DOutputBaseFilename=ocr-snap-v5.1.0-win /DIconFile=<app.ico> installer.iss
;
; A per-user install (no administrator rights) into
; %LOCALAPPDATA%\Programs\OCR Snap. The OCR engine the app downloads on
; first run lives apart from it, in %LOCALAPPDATA%\ocr-snap; uninstalling
; asks whether to remove that too.

#ifndef AppVersion
  #error AppVersion must be defined
#endif

[Setup]
AppId={{A62F9964-DE6E-4475-96F3-12DAFF1D3640}
AppName=OCR Snap
AppVersion={#AppVersion}
AppVerName=OCR Snap {#AppVersion}
AppPublisher=blyat-uk
AppPublisherURL=https://github.com/blyat-uk/ocr-snap
AppSupportURL=https://github.com/blyat-uk/ocr-snap/issues
DefaultDirName={localappdata}\Programs\OCR Snap
DefaultGroupName=OCR Snap
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\OCR Snap.exe
UninstallDisplayName=OCR Snap
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An upgrade replaces the whole tree: files a new version dropped must not linger.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\src"

[Icons]
Name: "{autoprograms}\OCR Snap"; Filename: "{app}\OCR Snap.exe"
Name: "{autoprograms}\OCR Snap (OCR engine setup)"; Filename: "{app}\OCR Snap.exe"; Parameters: "--setup-engine"; Comment: "Switch the OCR engine between the GPU and CPU builds, or reinstall it"
Name: "{autodesktop}\OCR Snap"; Filename: "{app}\OCR Snap.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OCR Snap.exe"; Description: "{cm:LaunchProgram,OCR Snap}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Engine: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Engine := ExpandConstant('{localappdata}\ocr-snap');
    if DirExists(Engine) then
      if SuppressibleMsgBox('Also remove the downloaded OCR engine and logs?' + #13#10 + #13#10 + Engine,
                            mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(Engine, True, True, True);
  end;
end;
