[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Check-Admin {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Check-Admin)) {
    Write-Host "[-] Error: Firewall requires Administrator privileges." -ForegroundColor Red
    Write-Host "[*] Attempting to relaunch as Administrator..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$ruleNames = @(
    "Hive Core (App Bound)",
    "Hive Agent (App Bound)",
    "Hive Control UDP",
    "Hive Control TCP",
    "Hive P2P Transfer"
)

foreach ($name in $ruleNames) {
    $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Remove-NetFirewallRule
        Write-Host "Removed firewall rule: $name"
    }
}

Write-Host "Hive firewall cleanup complete."
