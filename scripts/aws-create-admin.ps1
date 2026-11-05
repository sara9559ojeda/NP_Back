<#
.SYNOPSIS
    Creates the first administrator inside the running NP_Back task (ECS Exec).

.DESCRIPTION
    Opens an interactive session in the backend container and runs "python -m app.cli create-admin",
    which asks for the name, e-mail and password in the terminal. The password is never passed as an
    argument, so it is not stored in any log or shell history.
    Needs the Session Manager plugin for the AWS CLI.
#>
[CmdletBinding()]
param([string]$Parameters = 'parameters.json')

$ErrorActionPreference = 'Stop'
$InfraDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'infra\aws'
if (-not (Get-Command 'session-manager-plugin' -ErrorAction SilentlyContinue)) {
    throw 'Falta el Session Manager plugin: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html'
}
$Region = (Get-Content (Join-Path $InfraDir $Parameters) -Raw | ConvertFrom-Json).region
$Outputs = Get-Content (Join-Path $InfraDir 'outputs.json') -Raw | ConvertFrom-Json
$App = $Outputs.PSObject.Properties | Where-Object { $_.Name -like '*App' } | Select-Object -First 1 -ExpandProperty Value

$Task = aws ecs list-tasks --cluster $App.ClusterName --service-name $App.ServiceName --desired-status RUNNING --region $Region --query 'taskArns[0]' --output text
if ($LASTEXITCODE -ne 0 -or -not $Task -or $Task -eq 'None') { throw 'No hay ninguna tarea del backend en marcha.' }

aws ecs execute-command --cluster $App.ClusterName --task $Task --container $App.ContainerName --region $Region --interactive --command 'python -m app.cli create-admin'
