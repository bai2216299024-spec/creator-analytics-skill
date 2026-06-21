param(
    [string]$PythonExe = "",
    [string]$DataDir = "",
    [string]$Date = "",
    [string]$Platform = "all",
    [switch]$Headed
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillDir = Split-Path -Parent $ScriptDir
$SkillScript = Join-Path $ScriptDir "one_click_review.py"

if (-not $PythonExe) {
    $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $Candidates = @(
        $env:CREATOR_ANALYTICS_PYTHON,
        $CodexPython,
        "python"
    ) | Where-Object { $_ }

    foreach ($Candidate in $Candidates) {
        if ($Candidate -eq "python") {
            $Command = Get-Command python -ErrorAction SilentlyContinue
            if ($Command) {
                $PythonExe = $Command.Source
                break
            }
        } elseif (Test-Path -LiteralPath $Candidate) {
            $PythonExe = $Candidate
            break
        }
    }
}

if (-not $PythonExe) {
    throw "Python runtime not found. Set CREATOR_ANALYTICS_PYTHON or pass -PythonExe."
}

if (-not $DataDir) {
    $DataDir = Join-Path $SkillDir "data"
}

$LogDir = Join-Path $DataDir "logs"
$LogFile = Join-Path $LogDir ("creator-analytics-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

if (-not (Test-Path -LiteralPath $SkillScript)) {
    throw "creator-analytics entrypoint not found: $SkillScript"
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Start-Transcript -Path $LogFile -Append | Out-Null

try {
    Write-Host ("Started creator analytics daily review at " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
    $Args = @($SkillScript, "--data-dir", $DataDir, "--platform", $Platform)
    if ($Date) {
        $Args += @("--date", $Date)
    }
    if ($Headed) {
        $Args += "--headed"
    }

    & $PythonExe @Args
    $exitCode = $LASTEXITCODE
    Write-Host ("Finished creator analytics daily review at " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " with exit code " + $exitCode)
} catch {
    $exitCode = 1
    Write-Error $_
} finally {
    Stop-Transcript | Out-Null
}

exit $exitCode
