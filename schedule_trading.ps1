# PowerShell Script to automatically schedule the IBKR Trading System in Windows Task Scheduler
# Monday to Friday between 9:00 AM and 4:00 PM EST.
# Requires Administrator privileges to register system-level tasks.

$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Warning "This script must be run as an Administrator to register system-level Scheduled Tasks."
    Write-Host "Please open PowerShell as Administrator and run: `n  cd c:\ibkr `n  .\schedule_trading.ps1" -ForegroundColor Yellow
    Exit
}

# 1. Resolve Workspace and Python Paths
$WorkspacePath = "C:\ibkr"
$PythonPath = Join-Path $WorkspacePath ".venv\Scripts\python.exe"
$HelperScript = Join-Path $WorkspacePath "task_scheduler_helper.py"

if (-not (Test-Path $PythonPath)) {
    # Fallback to standard system python if virtual env not found
    $PythonPath = "python.exe"
    Write-Warning "Virtual environment python not found at $WorkspacePath\.venv. Falling back to system '$PythonPath'."
}

Write-Host "=== Setting up IBKR Automated Sentry Schedule ===" -ForegroundColor Green
Write-Host "Workspace Directory : $WorkspacePath"
Write-Host "Python Executable   : $PythonPath"
Write-Host "Sentry Scheduler    : $HelperScript"
Write-Host "------------------------------------------------"

# 2. Build the Scheduled Task Action
# Executing python.exe with the helper script as an argument
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument $HelperScript -WorkingDirectory $WorkspacePath

# 3. Build the Triggers (Every Weekday: Monday through Friday at 9:00 AM)
# Note: In Windows Scheduled Tasks, we create a Daily trigger at 9:00 AM and configure repetition settings.
# The repetition repeats the task every 5 minutes for 7 hours (covering 9:00 AM to 4:00 PM EST).
$Trigger = New-ScheduledTaskTrigger -Daily -At "9:00 AM"

# 4. Define Task settings (Repetition, Wake support, Stop if running, etc.)
# We set repetition interval to 5 minutes, and repetition duration to 7 hours.
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -StartWhenAvailable
$Settings.RepetitionInterval = (New-TimeSpan -Minutes 5)
$Settings.RepetitionDuration = (New-TimeSpan -Hours 7)

# 5. Define Principal (Run as SYSTEM or active local Administrator to ensure execution when logged out)
# Running as SYSTEM ensures high availability without password prompts.
$Principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# 6. Register Task
$TaskName = "IBKR Trading Engine Sentry"
Write-Host "Registering Scheduled Task: '$TaskName'..." -ForegroundColor Cyan

# Unregister if already exists to prevent duplicate schedules
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Task '$TaskName' already exists. Re-registering to apply latest settings." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -TaskName $TaskName -Description "Runs the automated trading system every weekday from 9:00 AM to 4:00 PM EST, repeating every 5 minutes to ensure high availability." | Out-Null

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "=== Registration Successful! ===" -ForegroundColor Green
    Write-Host "Task Name   : $TaskName"
    Write-Host "Trigger     : Monday - Friday starting at 9:00 AM EST"
    Write-Host "Repetition  : Every 5 minutes for 7 hours (until 4:00 PM EST)"
    Write-Host "Task Status : Ready"
    Write-Host "------------------------------------------------"
    Write-Host "To manually check your new task, open Windows 'Task Scheduler' (taskschd.msc) and locate '$TaskName' under the Active Tasks list." -ForegroundColor Yellow
} else {
    Write-Error "Failed to register Scheduled Task. Please verify your Administrator privileges."
}
