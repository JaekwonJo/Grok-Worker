Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

basePath = fso.GetParentFolderName(WScript.ScriptFullName)
profilePath = basePath & "\runtime\edge_attach_profile"
configPath = basePath & "\grok_worker_config_worker1.json"
If Not fso.FileExists(configPath) Then
    configPath = basePath & "\grok_worker_config.json"
End If

If Not fso.FolderExists(profilePath) Then
    fso.CreateFolder(profilePath)
End If

WshShell.CurrentDirectory = basePath
checkPyw = WshShell.Run("cmd /c where pythonw >nul 2>&1", 0, True)
checkPy = WshShell.Run("cmd /c where python >nul 2>&1", 0, True)
checkPyLauncher = WshShell.Run("cmd /c where py >nul 2>&1", 0, True)
launcherCmd = ""
If checkPyw = 0 Then
    launcherCmd = "pythonw """ & basePath & "\edge_launcher.py"" --port 9222 --profile-dir """ & profilePath & """ --config """ & configPath & """ --url ""https://grok.com/imagine"""
ElseIf checkPy = 0 Then
    launcherCmd = "python """ & basePath & "\edge_launcher.py"" --port 9222 --profile-dir """ & profilePath & """ --config """ & configPath & """ --url ""https://grok.com/imagine"""
ElseIf checkPyLauncher = 0 Then
    launcherCmd = "py """ & basePath & "\edge_launcher.py"" --port 9222 --profile-dir """ & profilePath & """ --config """ & configPath & """ --url ""https://grok.com/imagine"""
End If
If launcherCmd <> "" Then
    WshShell.Run "cmd /c reg add ""HKCU\Software\Policies\Microsoft\Edge"" /v VisualSearchEnabled /t REG_DWORD /d 0 /f >nul 2>&1 && reg add ""HKCU\Software\Policies\Microsoft\Edge"" /v SearchForImageEnabled /t REG_DWORD /d 0 /f >nul 2>&1 && " & launcherCmd, 0, False
End If

Set fso = Nothing
Set WshShell = Nothing
