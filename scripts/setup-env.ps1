<#
.SYNOPSIS
Project Panopticon - Environment Setup Script
Zero-touch environment bootstrapping for Sovereign Native deployment.

.DESCRIPTION
Verifies prerequisites, creates Python venv, installs dependencies,
initializes storage, and clones vendor repos. Idempotent - safe to re-run.

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
# 1. Bootstrap: Ensure PowerShell 7+
# ============================================================================
Write-Step "Bootstrap: Checking PowerShell version"

$pwshPath = Get-Command pwsh -ErrorAction SilentlyContinue
if (-not $pwshPath) {
    Write-Error "PowerShell 7+ (pwsh) not found. Please install from https://github.com/PowerShell/PowerShell"
    exit 1
}

Write-Success "PowerShell 7+ detected: $($pwshPath.Source)"
$pwshVersion = & pwsh --version
Write-ColorOutput "  Version: $pwshVersion" -Color "Gray"

# ============================================================================
# 2. Prerequisite Verification
# ============================================================================
Write-Step "Prerequisite Verification"

$prereqs = @(
    @{ Name = "Python"; Command = "python --version"; MinVersion = "3.12" }
    @{ Name = "Node.js"; Command = "node --version"; MinVersion = "18" }
    @{ Name = "npm"; Command = "npm --version"; MinVersion = "9" }
    @{ Name = "Git"; Command = "git --version"; MinVersion = "2.0" }
    @{ Name = "SurrealDB CLI"; Command = "surreal --version"; MinVersion = "1.0" }
    @{ Name = "NATS Server"; Command = "nats-server --version"; MinVersion = "2.0" }
)

$missing = @()

foreach ($prereq in $prereqs) {
    $versionOutput = & $prereq.Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$($prereq.Name) not found on PATH"
        $missing += $prereq.Name
        continue
    }

    # Parse version (e.g., "Python 3.12.0" or "Node.js v18.17.0")
    $version = $versionOutput | Select-String -Pattern "(\d+\.\d+\.\d+)" | ForEach-Object { $_.Matches.Groups[1].Value }
    if (-not $version) {
        Write-Warning "$($prereq.Name) version could not be parsed: $versionOutput"
        $missing += $prereq.Name
        continue
    }

    # Compare versions
    $versionParts = $version -split "\."
    $minParts = $prereq.MinVersion -split "\."

    $satisfied = $true
    for ($i = 0; $i -lt $minParts.Count; $i++) {
        if ([int]$versionParts[$i] -lt [int]$minParts[$i]) {
            $satisfied = $false
            break
        }
    }

    if ($satisfied) {
        Write-Success "$($prereq.Name): $version"
    } else {
        Write-Error "$($prereq.Name): $version (requires $($prereq.MinVersion)+)"
        $missing += $prereq.Name
    }
}

if ($missing.Count -gt 0) {
    Write-Error "`nMissing prerequisites: $($missing -join ', ')"
    Write-ColorOutput "`nPlease install missing tools and add them to your PATH." -Color "Yellow"
    exit 1
}

# ============================================================================
# 3. Python Virtual Environment
# ============================================================================
Write-Step "Python Virtual Environment"

$venvPath = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-ColorOutput "Creating Python venv at $venvPath..." -Color "Cyan"
    & python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create Python venv"
        exit 1
    }
    Write-Success "Python venv created"
} else {
    Write-Success "Python venv already exists"
}

# Activate venv
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
& $activateScript

# ============================================================================
# 4. Install Python Dependencies
# ============================================================================
Write-Step "Python Dependencies"

$requirementsPath = Join-Path $ProjectRoot "backend\requirements.txt"
if (-not (Test-Path $requirementsPath)) {
    Write-Error "backend/requirements.txt not found"
    exit 1
}

Write-ColorOutput "Installing Python dependencies..." -Color "Cyan"
& pip install --upgrade pip
& pip install -r $requirementsPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install Python dependencies"
    exit 1
}
Write-Success "Python dependencies installed"

# ============================================================================
# 5. Frontend Dependencies
# ============================================================================
Write-Step "Frontend Dependencies"

$frontendPath = Join-Path $ProjectRoot "frontend"
if (-not (Test-Path $frontendPath)) {
    Write-Error "frontend/ directory not found"
    exit 1
}

Write-ColorOutput "Installing Node.js dependencies..." -Color "Cyan"
& npm install
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install Node.js dependencies"
    exit 1
}
Write-Success "Node.js dependencies installed"

# ============================================================================
# 6. Persistent Storage Initialization
# ============================================================================
Write-Step "Persistent Storage"

$dataPath = Join-Path $ProjectRoot ".panopticon\data"
if (-not (Test-Path $dataPath)) {
    Write-ColorOutput "Creating .panopticon/data directory..." -Color "Cyan"
    New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
}

$dataReadme = Join-Path $dataPath "README.md"
if (-not (Test-Path $dataReadme)) {
    $content = "# Panopticon Persistent Storage`r`n`r`nThis directory contains the SurrealDB database file (panopticon.db) using the surrealkv backend. All geospatial data, aircraft telemetry, and OSINT events are persisted here.`r`n`r`n**Note**: This directory is git-ignored to prevent committing sensitive data."
    Set-Content -Path $dataReadme -Value $content -Encoding UTF8
    Write-Success "Storage marker created"
} else {
    Write-Success "Storage already initialized"
}

# ============================================================================
# 7. Environment File Generation
# ============================================================================
Write-Step "Environment Configuration"

$envExamplePath = Join-Path $ProjectRoot ".env.example"
$envPath = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $envExamplePath)) {
    Write-Error ".env.example not found"
    exit 1
}

if (-not (Test-Path $envPath)) {
    Write-ColorOutput "Generating .env from .env.example..." -Color "Cyan"
    Copy-Item -Path $envExamplePath -Destination $envPath
    Write-Warning ".env file generated. Please populate it with your API keys."
} else {
    Write-Success ".env already exists (skipping generation)"
}

# ============================================================================
# 8. Vendor Repositories
# ============================================================================
Write-Step "Vendor Repositories"

$vendorPath = Join-Path $ProjectRoot "vendor"
$twitterRepo = "https://github.com/om-ashish-soni/headless-twitter.git"
$twitterPath = Join-Path $vendorPath "headless-twitter"

if (-not (Test-Path $twitterPath)) {
    Write-ColorOutput "Cloning headless-twitter repository..." -Color "Cyan"
    & git clone $twitterRepo $twitterPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to clone headless-twitter repository"
        exit 1
    }
    Write-Success "headless-twitter cloned"
} else {
    Write-Success "headless-twitter already exists (skipping clone)"
}

# ============================================================================
# 9. Summary
# ============================================================================
Write-ColorOutput "`n" -NoNewline
Write-ColorOutput "╔══════════════════════════════════════════════════════════════╗" -Color "Green"
Write-ColorOutput "║  Project Panopticon - Environment Setup Complete!           ║" -Color "Green"
Write-ColorOutput "╚══════════════════════════════════════════════════════════════╝" -Color "Green"
Write-ColorOutput "`nNext steps:" -Color "Cyan"
Write-ColorOutput "  1. Edit .env and add your API keys" -Color "White"
Write-ColorOutput "  2. Run: .\scripts\launch-panopticon.ps1" -Color "White"
Write-ColorOutput "`n" -NoNewline