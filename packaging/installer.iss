; Truffle 安装包脚本（Inno Setup 6）
; 编译：ISCC.exe packaging\installer.iss  （或直接跑 packaging\build.ps1）
; 产物：dist\installer\Truffle-Setup-<版本>.exe
;
; 说明：按用户安装（PrivilegesRequired=lowest），不需要管理员权限，
;       默认装到 %LOCALAPPDATA%\Programs\Truffle。

#define MyAppName "Truffle"
; 版本号可由命令行覆盖：ISCC /DMyAppVersion=0.0.2 installer.iss
#ifndef MyAppVersion
  #define MyAppVersion "0.0.1"
#endif
#define MyAppExeName "Truffle.exe"

[Setup]
AppId={{AEF7C5FD-6CC9-4502-9933-BF10F19DB6FE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Truffle-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\assets\truffle.ico
; 升级覆盖时，尝试关闭正在运行的旧程序，装完不自动重启
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[InstallDelete]
; 安装前清掉上一版遗留的运行时目录与主程序，保证「完整覆盖」而非只盖同名文件
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"

[Files]
Source: "..\dist\Truffle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
