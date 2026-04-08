Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

basePath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = basePath

checkPyw = WshShell.Run("cmd /c where pythonw >nul 2>&1", 0, True)
checkPy = WshShell.Run("cmd /c where python >nul 2>&1", 0, True)
fallbackBat = basePath & "\2_Grok_Worker_실행.bat"

If checkPyw = 0 Then
    WshShell.Run "cmd /c pythonw main.py", 0
ElseIf checkPy = 0 Then
    WshShell.Run "cmd /c python main.py", 0
ElseIf fso.FileExists(fallbackBat) Then
    WshShell.Run """" & fallbackBat & """", 1
Else
    MsgBox "Python launcher was not found." & vbCrLf & _
           "Please run 0_원터치_설치+실행.bat first.", vbExclamation, "Grok Worker"
End If

Set fso = Nothing
Set WshShell = Nothing

