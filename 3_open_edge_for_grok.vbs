Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

basePath = fso.GetParentFolderName(WScript.ScriptFullName)
profilePath = basePath & "\runtime\edge_attach_profile"

If Not fso.FolderExists(profilePath) Then
    fso.CreateFolder(profilePath)
End If

WshShell.CurrentDirectory = basePath
WshShell.Run "cmd /c start """" msedge --remote-debugging-port=9222 --user-data-dir=""""" & profilePath & """"" --new-window https://grok.com/imagine", 0, False

Set fso = Nothing
Set WshShell = Nothing
