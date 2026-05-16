<#
.SYNOPSIS
Project Panopticon - Stack Launcher
Multi-terminal stack launcher for SurrealDB, NATS, FastAPI, and Vite.

.DESCRIPTION
Launches all 4 stack components in separate, visible PowerShell terminals.
Each component runs in its own window for visibility and debugging.

.NOTES
Author: Project Panopticon Team
Version: 1.0
#>

# Exit on any error
$ErrorActionPreference = "Stop"

# Script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Color output
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Step {
    param([string]$Message)
    Write-ColorOutput "`n[$Message]" -Color "Cyan"
}

function Write-Success {
    param([string]$Message)
    Write-ColorOutput "✓ $Message" -Color "Green"
}

function Write-Error {
    param([string]$Message)
    Write-ColorOutput "✗ $Message" -Color "Red"
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "⚠ $Message" -Color "Yellow"
}

# ============================================================================
# 1. Load Environment
# ============================================================================
Write-Step "Loading Environment Configuration"

$envPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Error ".env file not found. Please run setup-env.ps1 first."
    exit 1
}

Write-ColorOutput "Loading .env file..." -Color "Cyan"
Get-Content $envPath | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}
Write-Success "Environment loaded"

# ============================================================================
# 2. Resolve Paths
# ============================================================================
Write-Step "Resolving Component Paths"

$venvPath = Join-Path $ProjectRoot ".venv"
$frontendPath = Join-Path $ProjectRoot "frontend"
$binPath = Join-Path $ProjectRoot "bin"

# Check if SurrealDB is on PATH
$surrealCmd = Get-Command surreal -ErrorAction SilentlyContinue
if (-not $surrealCmd) {
    Write-Error "SurrealDB CLI not found on PATH. Please run setup-env.ps1."
    exit 1
}
Write-Success "SurrealDB: $($surrealCmd.Source)"

# Check if NATS is on PATH
$natsCmd = Get-Command nats-server -ErrorAction SilentlyContinue
if (-not $natsCmd) {
    Write-Error "NATS Server not found on PATH. Please run setup-env.ps1."
    exit 1
}
Write-Success "NATS: $($natsCmd.Source)"

# Check if Python is available
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "Python not found on PATH. Please run setup-env.ps1."
    exit 1
}
Write-Success "Python: $($pythonCmd.Source)"

# Check if npm is available
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Error "npm not found on PATH. Please run setup-env.ps1."
    exit 1
}
Write-Success "npm: $($npmCmd.Source)"

# ============================================================================
# 3. Component Configuration
# ============================================================================
Write-Step "Component Configuration"

$components = @(
    @{
        Name = "SurrealDB"
        Title = "Panopticon: SurrealDB"
        Command = "surreal start --log info --user root --pass root --bind 127.0.0.1:8000 surrealkv:.panopticon/data/panopticon.db"
        Port = 8000
    },
    @{
        Name = "NATS"
        Title = "Panopticon: NATS"
        Command = "nats-server -p 4222"
        Port = 4222
    },
    @{
        Name = "FastAPI"
        Title = "Panopticon: FastAPI"
        Command = ".venv\Scripts\activate && uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload"
        Port = 8080
    },
    @{
        Name = "Vite"
        Title = "Panopticon: Vite"
        Command = "npm run dev"
        Port = 5173
    }
)

# ============================================================================
# 4. Check Ports
# ============================================================================
Write-Step "Port Availability Check"

$portsInUse = @()
foreach ($component in $components) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $tcp.Connect("127.0.0.1", $component.Port)
        $tcp.Close()
        $portsInUse += $component.Port
    } catch {
        # Port is available
    }
}

if ($portsInUse.Count -gt 0) {
    Write-Warning "The following ports are already in use: $($portsInUse -join ', ')"
    Write-ColorOutput "This may cause conflicts. Please stop the services using these ports first." -Color "Yellow"
    $response = Read-Host "`nContinue anyway? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-ColorOutput "Aborted." -Color "Red"
        exit 1
    }
}

# ============================================================================
# 5. Launch Components
# ============================================================================
Write-Step "Launching Components"

$processes = @()

foreach ($component in $components) {
    Write-ColorOutput "`nLaunching $($component.Name)..." -Color "Cyan"

    $process = Start-Process -FilePath "pwsh" `
        -ArgumentList "-NoExit", "-Command", $component.Command `
        -WindowStyle Normal `
        -PassThru

    $processes += @{
        Process = $process
        Name = $component.Name
        Title = $component.Title
        Port = $component.Port
    }

    Write-Success "$($component.Name) started (PID: $($process.Id))"

    # Stagger launches to avoid overwhelming the system
    Start-Sleep -Seconds 2
}

# ============================================================================
# 6. Summary
# ============================================================================
Write-ColorOutput "`n" -NoNewline
Write-ColorOutput "╔══════════════════════════════════════════════════════════════╗" -Color "Green"
Write-ColorOutput "║  Project Panopticon - Stack Launched Successfully!          ║" -Color "Green"
Write-ColorOutput "╚══════════════════════════════════════════════════════════════╝" -Color "Green"
Write-ColorOutput "`nComponent Status:" -Color "Cyan"
foreach ($proc in $processes) {
    Write-ColorOutput "  • $($proc.Name): PID $($proc.Process.Id) (Port $($proc.Port))" -Color "White"
}
Write-ColorOutput "`nAccess Points:" -Color "Cyan"
Write-ColorOutput "  • SurrealDB: http://127.0.0.1:8000" -Color "White"
Write-ColorOutput "  • FastAPI: http://127.0.0.1:8080/api/health" -Color "White"
Write-ColorOutput "  • Vite: http://localhost:5173" -Color "White"
Write-ColorOutput "`n" -NoNewline

# ============================================================================
# 7. Cleanup Handler
# ============================================================================
Write-ColorOutput "Press Ctrl+C in this terminal to stop all components." -Color "Yellow"

$running = $true
while ($running) {
    Start-Sleep -Seconds 1

    # Check if any process is still running
    $allRunning = $true
    foreach ($proc in $processes) {
        if (-not $proc.Process.HasExited) {
            $allRunning = $true
            break
        }
    }

    if (-not $allRunning) {
        Write-ColorOutput "`nOne or more components have stopped." -Color "Yellow"
        $response = Read-Host "Stop all components? (Y/n)"
        if ($response -eq "" -or $response -eq "y" -or $response -eq "Y") {
            $running = $false
        }
    }
}

# Stop all processes
Write-Step "Stopping Components"
foreach ($proc in $processes) {
    if (-not $proc.Process.HasExited) {
        Write-ColorOutput "Stopping $($proc.Name) (PID: $($proc.Process.Id))..." -Color "Cyan"
        $proc.Process.Kill()
        Write-Success "$($proc.Name) stopped"
    }
}

Write-ColorOutput "`nAll components stopped." -Color "Green"
Write-ColorOutput "`n" -NoNewline