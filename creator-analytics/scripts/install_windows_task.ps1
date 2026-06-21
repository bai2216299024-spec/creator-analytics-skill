param(
    [string]$TaskName = "CreatorAnalyticsDailyReview",
    [string]$At = "00:00",
    [string]$PythonExe = "",
    [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "run_daily_review.ps1"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Daily runner not found: $Runner"
}

$Args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$Runner`""
)

if ($PythonExe) {
    $Args += @("-PythonExe", "`"$PythonExe`"")
}

if ($DataDir) {
    $Args += @("-DataDir", "`"$DataDir`"")
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($Args -join " ")
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Run creator-analytics one-click daily review" `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Format-List TaskName,State,TaskPath
