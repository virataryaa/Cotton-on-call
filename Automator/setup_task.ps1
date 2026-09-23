# Registers the weekly Cotton On-Call update in Windows Task Scheduler.
# CFTC releases the report Thursday ~3:30pm ET; this runs Friday morning
# local time to give the release (and any holiday delay) a safety margin.
# Run this script once, as the user who should own the scheduled task.

$taskName = "Cotton On-Call Update"
$batPath  = Join-Path $PSScriptRoot "run_coc_update.bat"

$action  = New-ScheduledTaskAction -Execute $batPath
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 8:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Pulls new CFTC Cotton On-Call reports into the Cotton_Calls database." `
    -Force

Write-Host "Registered scheduled task '$taskName' (Fridays 8:00 AM)."
