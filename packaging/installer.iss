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
; 默认 auto 会在「覆盖安装」时隐藏安装目录页；强制显示，保证用户能确认/修改安装目录
DisableDirPage=no
OutputDir=..\dist\installer
OutputBaseFilename=Truffle-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\truffle.ico
SetupIconFile=..\assets\truffle.ico
; 升级覆盖时，尝试关闭正在运行的旧程序，装完不自动重启
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; 中文界面（覆盖 Inno 内置英文文案；[name]/[name/ver]/[mb]/%n 为占位符，必须保留）
SetupAppTitle=安装程序
SetupWindowTitle=安装 %1
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=即将在你的电脑上安装 [name/ver]。%n%n建议先关闭其它正在运行的程序，再继续。
SelectDirDesc=要安装到哪个文件夹？
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=点击「下一步」继续；如需更改安装位置，请点击「浏览」。
DiskSpaceMBLabel=本程序安装后大约占用 [mb] MB 磁盘空间。
SelectTasksDesc=要执行哪些附加任务？
SelectTasksLabel2=选择安装 [name] 时要执行的附加任务，然后点击「下一步」。
ReadyLabel1=安装向导已准备好开始安装 [name]。
ReadyLabel2a=点击「安装」开始安装，或点击「上一步」检查、修改设置。
ReadyLabel2b=点击「安装」开始安装。
InstallingLabel=正在安装 [name]，请稍候…
FinishedHeadingLabel=[name] 安装完成
FinishedLabel=安装已完成。
ButtonBack=< 上一步
ButtonNext=下一步 >
ButtonInstall=安装
ButtonCancel=取消
ButtonYes=是
ButtonNo=否
ButtonFinish=完成
ButtonBrowse=浏览…

[Registry]
; 注册 .truffle 项目文件（按用户，不需要管理员）
Root: HKCU; Subkey: "Software\Classes\.truffle"; ValueType: string; ValueName: ""; ValueData: "Truffle.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Truffle.Project"; ValueType: string; ValueName: ""; ValueData: "Truffle 项目"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Truffle.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\truffle.ico"",0"
Root: HKCU; Subkey: "Software\Classes\Truffle.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Truffle.exe"" ""%1"""

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："

[InstallDelete]
; 安装前清掉上一版遗留的运行时目录与主程序，保证「完整覆盖」而非只盖同名文件
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"

[UninstallDelete]
; 卸载时彻底清掉安装目录（含运行期生成的 log 等未登记残留），保证「完全卸载软件本体」
Type: filesandordirs; Name: "{app}"

[Files]
Source: "..\dist\Truffle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 显式把主图标放到安装根目录：快捷方式用它当图标，不再依赖 exe 内嵌图标（避免升级后图标缓存不刷新）
Source: "..\assets\truffle.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 显式指定 IconFilename（否则快捷方式图标继承自目标 exe，升级到同一路径时 Windows 图标缓存可能仍显示旧图标）
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\truffle.ico"; IconIndex: 0
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\truffle.ico"; IconIndex: 0
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\truffle.ico"; IconIndex: 0; Tasks: desktopicon

[Run]
; 刷新 Windows 图标缓存，确保桌面/开始菜单立刻显示新图标（覆盖安装同一路径时尤为重要）
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden skipifdoesntexist
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
{ 统计某个目录的总字节数（递归）。 }
function GetDirSize(const Dir: String): Int64;
var
  FindRec: TFindRec;
  Sub: String;
begin
  Result := 0;
  Sub := AddBackslash(Dir);
  if FindFirst(Sub + '*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            Result := Result + GetDirSize(Sub + FindRec.Name)
          else
            Result := Result + Int64(FindRec.SizeHigh) * 4294967296 + FindRec.SizeLow;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

{ 完成页：告知用户安装位置与实际占用磁盘。 }
procedure CurPageChanged(CurPageID: Integer);
var
  MB: Integer;
begin
  if CurPageID = wpFinished then
  begin
    MB := Integer(GetDirSize(ExpandConstant('{app}')) div (1024 * 1024));
    WizardForm.FinishedLabel.Caption :=
      '安装位置：' + ExpandConstant('{app}') + #13#10 +
      '实际占用磁盘：约 ' + IntToStr(MB) + ' MB';
  end;
end;

{ 确认安装页（Ready）：汇总「安装目录 / 是否创建快捷方式 / 预计占用磁盘」。 }
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '安装目录：' + ExpandConstant('{app}') + NewLine;
  if WizardIsTaskSelected('desktopicon') then
    S := S + '创建桌面快捷方式：是' + NewLine
  else
    S := S + '创建桌面快捷方式：否' + NewLine;
  if WizardForm.DiskSpaceLabel.Caption <> '' then
    S := S + WizardForm.DiskSpaceLabel.Caption + NewLine;
  S := S + NewLine + '点击「安装」开始安装。';
  Result := S;
end;
