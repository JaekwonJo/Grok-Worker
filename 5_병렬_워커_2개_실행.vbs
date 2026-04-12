Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

basePath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = basePath

checkPyw = WshShell.Run("cmd /c where pythonw >nul 2>&1", 0, True)
checkPy = WshShell.Run("cmd /c where python >nul 2>&1", 0, True)
checkPyLauncher = WshShell.Run("cmd /c where py >nul 2>&1", 0, True)

If checkPyw = 0 Then
    WshShell.Run "cmd /c pythonw parallel_launcher.py 2", 0, False
ElseIf checkPy = 0 Then
    WshShell.Run "cmd /c python parallel_launcher.py 2", 0, False
ElseIf checkPyLauncher = 0 Then
    WshShell.Run "cmd /c py parallel_launcher.py 2", 0, False
Else
    MsgBox "Python launcher was not found." & vbCrLf & _
           "Please run 0_원터치_설치+실행.bat first.", vbExclamation, "Grok Worker"
End If

Set fso = Nothing
Set WshShell = Nothing
