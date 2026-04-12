Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

basePath = fso.GetParentFolderName(WScript.ScriptFullName)
profilePath = basePath & "\runtime\edge_attach_profile_2"

If Not fso.FolderExists(profilePath) Then
    fso.CreateFolder(profilePath)
End If

WshShell.CurrentDirectory = basePath
WshShell.Run "cmd /c reg add ""HKCU\Software\Policies\Microsoft\Edge"" /v VisualSearchEnabled /t REG_DWORD /d 0 /f >nul 2>&1 && reg add ""HKCU\Software\Policies\Microsoft\Edge"" /v SearchForImageEnabled /t REG_DWORD /d 0 /f >nul 2>&1 && start """" msedge --remote-debugging-port=9223 --user-data-dir=""""" & profilePath & """"" --disable-features=msDownloadsHub,DownloadBubble,DownloadBubbleV2 --new-window https://grok.com/imagine", 0, False

Set fso = Nothing
Set WshShell = Nothing
