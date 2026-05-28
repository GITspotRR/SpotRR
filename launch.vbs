Dim fso, sDir, sPython, sScript
Set fso = CreateObject("Scripting.FileSystemObject")
sDir   = fso.GetParentFolderName(WScript.ScriptFullName)
sPython = sDir & "\.venv\Scripts\pythonw.exe"
sScript = sDir & "\spotrr.py"

If fso.FileExists(sPython) Then
    CreateObject("WScript.Shell").Run Chr(34) & sPython & Chr(34) & " " & Chr(34) & sScript & Chr(34), 0, False
Else
    MsgBox "Virtual environment not found." & vbCrLf & "Please run setup.bat first.", 16, "SpotRR"
End If
