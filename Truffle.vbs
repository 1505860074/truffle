' Truffle 隐藏终端启动器
' 首次运行（环境未就绪）：显示控制台完成依赖安装
' 之后运行：直接用 pythonw 无控制台启动软件
Option Explicit
Dim fso, sh, root, pyw, bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = root & "\.venv\Scripts\pythonw.exe"
bat = root & "\Truffle.bat"

sh.CurrentDirectory = root

If fso.FileExists(pyw) Then
    sh.Run """" & pyw & """ """ & root & "\run.py""", 0, False
Else
    sh.Run """" & bat & """", 1, False
End If
