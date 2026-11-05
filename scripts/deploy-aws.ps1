<#
.SYNOPSIS
    Deploys NEUROPHOBIA (NP_Back + NP_Front) to AWS with the CDK app in infra/aws.

.DESCRIPTION
    1. Checks the tools and the AWS credentials.
    2. Builds NP_Front against the real API (/api/v1, no mocks).
    3. Bootstraps CDK in the target account and Region (idempotent).
    4. Runs cdk deploy for both stacks and prints the URLs.

    Nothing secret is read or printed: every secret is generated in, or read from,
    AWS Secrets Manager by the stacks themselves.

.PARAMETER Parameters
    Parameters file, relative to infra/aws. Default: parameters.json.

.PARAMETER Yes
    Skip the interactive approval of IAM and security group changes.

.EXAMPLE
    .\scripts\deploy-aws.ps1
#>
[CmdletBinding()]
param(
    [string]$Parameters = 'parameters.json',
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$BackendRoot = Split-Path -Parent $PSScriptRoot
$InfraDir = Join-Path $BackendRoot 'infra\aws'

function Invoke-Native {
    param([string]$Step, [scriptblock]$Command)
    Write-Host "==> $Step" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Fallo en el paso: $Step (codigo $LASTEXITCODE)" }
}

function Assert-Tool {
    param([string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Falta '$Name'. $Hint" }
}

Assert-Tool 'aws' 'Instala AWS CLI v2: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html'
Assert-Tool 'node' 'Instala Node.js 20.19 o superior.'
Assert-Tool 'npm' 'Instala Node.js 20.19 o superior.'
Assert-Tool 'docker' 'Instala Docker Desktop y arrancalo.'
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker no esta en marcha. Arranca Docker Desktop y vuelve a intentarlo.' }

$ParametersPath = Join-Path $InfraDir $Parameters
if (-not (Test-Path $ParametersPath)) {
    throw "No existe $ParametersPath. Copia infra\aws\parameters.example.json a infra\aws\parameters.json y revisalo."
}
$Config = Get-Content $ParametersPath -Raw | ConvertFrom-Json
$Region = $Config.region
$FrontendDir = Join-Path $BackendRoot $Config.frontend.sourceDir
if (-not (Test-Path (Join-Path $FrontendDir 'package.json'))) { throw "No se encuentra NP_Front en $FrontendDir (frontend.sourceDir)." }

$Account = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or -not $Account) { throw 'No hay credenciales de AWS validas. Ejecuta "aws configure" o "aws sso login".' }
if ($Config.account -and $Config.account -ne $Account) {
    throw "Las credenciales son de la cuenta $Account, pero parameters.json pide $($Config.account)."
}
Write-Host "Cuenta $Account, region $Region" -ForegroundColor Green

if ($Config.database.mode -eq 'external') {
    aws secretsmanager describe-secret --secret-id $Config.database.externalSecretName --region $Region --query Name --output text *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "No existe el secreto '$($Config.database.externalSecretName)' en $Region. Crealo primero (docs/DESPLIEGUE_AWS.md, seccion Supabase)."
    }
}

Push-Location $InfraDir
try {
    Invoke-Native 'Instalando dependencias de la infraestructura' { npm ci --no-audit --no-fund }
}
finally { Pop-Location }

Push-Location $FrontendDir
try {
    Invoke-Native 'Instalando dependencias de NP_Front' { npm ci --no-audit --no-fund }
    $env:VITE_API_BASE_URL = '/api/v1'
    $env:VITE_USE_MOCKS = 'false'
    Invoke-Native 'Compilando NP_Front contra la API real' { npm run build }
}
finally {
    Remove-Item Env:VITE_API_BASE_URL, Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue
    Pop-Location
}

Push-Location $InfraDir
try {
    $env:CDK_DEFAULT_ACCOUNT = $Account
    $env:CDK_DEFAULT_REGION = $Region
    Invoke-Native 'Preparando CDK en la cuenta (bootstrap)' { npx cdk bootstrap "aws://$Account/$Region" -c "parameters=$Parameters" }
    $Approval = if ($Yes) { 'never' } else { 'broadening' }
    Invoke-Native 'Desplegando (puede tardar 15-25 minutos la primera vez)' {
        npx cdk deploy --all -c "parameters=$Parameters" --require-approval $Approval --outputs-file outputs.json
    }
    $Outputs = Get-Content (Join-Path $InfraDir 'outputs.json') -Raw | ConvertFrom-Json
    $App = $Outputs.PSObject.Properties | Where-Object { $_.Name -like '*App' } | Select-Object -First 1 -ExpandProperty Value
    Write-Host ''
    Write-Host 'Despliegue terminado.' -ForegroundColor Green
    Write-Host "  Web:              $($App.WebUrl)"
    Write-Host "  API (Unity):      $($App.ApiBaseUrl)"
    Write-Host "  Logs del backend: $($App.BackendLogGroup)"
    Write-Host ''
    Write-Host 'Siguiente paso: crear el primer administrador con .\scripts\aws-create-admin.ps1'
}
finally { Pop-Location }
