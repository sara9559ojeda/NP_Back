<#
.SYNOPSIS
    Removes the NEUROPHOBIA AWS deployment created by deploy-aws.ps1.

.DESCRIPTION
    Destroys the application stack, then lifts the termination protection of the data stack and
    destroys it. Amazon RDS keeps a final snapshot (it still costs storage until you delete it).
    The CDKToolkit bootstrap stack is kept: other CDK apps in the account may use it.

.PARAMETER Parameters
    Parameters file, relative to infra/aws. Default: parameters.json.
#>
[CmdletBinding()]
param([string]$Parameters = 'parameters.json')

$ErrorActionPreference = 'Stop'
$InfraDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'infra\aws'
$Config = Get-Content (Join-Path $InfraDir $Parameters) -Raw | ConvertFrom-Json
$Prefix = (($Config.projectName -split '-') | ForEach-Object { $_.Substring(0, 1).ToUpper() + $_.Substring(1) }) -join ''
$Region = $Config.region

Write-Host "Se borraran las pilas ${Prefix}App y ${Prefix}Data en $Region, con la base de datos." -ForegroundColor Yellow
Write-Host 'RDS guardara una instantanea final. Los datos de la web dejaran de estar disponibles.'
$Answer = Read-Host "Escribe '$($Config.projectName)' para confirmar"
if ($Answer -ne $Config.projectName) { Write-Host 'Cancelado.'; exit 1 }

Push-Location $InfraDir
try {
    npx cdk destroy "${Prefix}App" -c "parameters=$Parameters" --force
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo borrar la pila de la aplicacion.' }
    aws cloudformation update-termination-protection --no-enable-termination-protection --stack-name "${Prefix}Data" --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo quitar la proteccion de la pila de datos.' }
    npx cdk destroy "${Prefix}Data" -c "parameters=$Parameters" --force
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo borrar la pila de datos.' }
}
finally { Pop-Location }

Write-Host 'Listo. Revisa las instantaneas en RDS > Snapshots si quieres borrarlas tambien.' -ForegroundColor Green
