Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "C:\web\run_everything.bat" & Chr(34), 0
Set WshShell = Nothing