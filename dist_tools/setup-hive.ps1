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

# Resolve full paths to executables relative to script location
$HiveExe = Join-Path $PSScriptRoot "Hive.exe"
$AgentExe = Join-Path $PSScriptRoot "agents\win32\HiveAgent.exe"

$rules = @(
    @{ Name = "Hive Core (App Bound)"; Path = $HiveExe; Port = "5000-5011" },
    @{ Name = "Hive Agent (App Bound)"; Path = $AgentExe; Port = "5000-5011" }
)

foreach ($rule in $rules) {
    if (-not (Test-Path $rule.Path)) {
        Write-Host "[!] Warning: Executable not found at $($rule.Path). Skipping rule $($rule.Name)." -ForegroundColor Cyan
        continue
    }

    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -DisplayName $rule.Name -Enabled True -Direction Inbound -Action Allow -Program $rule.Path -Profile Any
        Set-NetFirewallPortFilter -AssociatedNetFirewallRule $existing -Protocol TCP -LocalPort $rule.Port
        Set-NetFirewallPortFilter -AssociatedNetFirewallRule $existing -Protocol UDP -LocalPort $rule.Port
        Write-Host "Updated port-restricted app-bound rule: $($rule.Name)"
    } else {
        # Create explicit rules for both TCP and UDP on Any profile
        New-NetFirewallRule -DisplayName "$($rule.Name) (TCP)" -Direction Inbound -Program $rule.Path -Protocol TCP -LocalPort $rule.Port -Action Allow -Profile Any | Out-Null
        New-NetFirewallRule -DisplayName "$($rule.Name) (UDP)" -Direction Inbound -Program $rule.Path -Protocol UDP -LocalPort $rule.Port -Action Allow -Profile Any | Out-Null
        Write-Host "Created port-restricted app-bound rules (TCP/UDP): $($rule.Name)"
    }
}

Write-Host "Firewall rules successfully bound to Hive executables."
