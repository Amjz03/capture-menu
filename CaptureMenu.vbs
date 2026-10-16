Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
If CreateObject("Scripting.FileSystemObject").FileExists(folder & "\CaptureMenu.exe") Then
    shell.Run """" & folder & "\start.bat"" exe", 0, False
Else
    shell.Run """" & folder & "\start.bat""", 0, False
End If
