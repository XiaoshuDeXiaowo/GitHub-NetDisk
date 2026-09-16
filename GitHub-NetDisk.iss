#ifndef MyAppVersion
  #define MyAppVersion "0.0.1"
#endif
#ifndef MyAppArch
  #define MyAppArch "x64compatible"
#endif
#ifndef MyArtifactArch
  #define MyArtifactArch "x86_64"
#endif

#define MyAppName "GitHub NetDisk"
#define MyAppPublisher "XiaoshuDeXiaowo"
#define MyAppURL "https://github-netdisk.top/"
#define MyAppExeName "GitHub-NetDisk.exe"

[Setup]
AppId={{A7A14388-E12C-4F84-B7D3-241552CD45CA}
AppName={cm:AppDisplayName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\GitHub-NetDisk
DefaultGroupName={cm:AppDisplayName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=GitHub-NetDisk-v{#MyAppVersion}-Windows-{#MyArtifactArch}-Setup
SetupIconFile=app/resource/images/logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed={#MyAppArch}
ArchitecturesInstallIn64BitMode={#MyAppArch}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "chinesetraditional"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"

[CustomMessages]
english.AppDisplayName=GitHub NetDisk
chinesesimplified.AppDisplayName=GitHub 网盘
chinesetraditional.AppDisplayName=GitHub 網盤

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\GitHub-NetDisk.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{cm:AppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{cm:AppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\github-netdisk"; ValueType: string; ValueName: ""; ValueData: "URL:GitHub-NetDisk Protocol"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\github-netdisk"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\github-netdisk\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\github-netdisk\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{cm:AppDisplayName}}"; Flags: nowait postinstall skipifsilent
