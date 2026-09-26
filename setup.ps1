# Modified for this distribution: fixed the PowerShell component prompt loop.
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $PSCommandPath
$managedBegin = '<!-- BEGIN codex-orchestrator:managed -->'
$managedEnd = '<!-- END codex-orchestrator:managed -->'
$legacyManagedBegin = '<!-- BEGIN codex-astra-luna-orchestrator:managed -->'
$legacyManagedEnd = '<!-- END codex-astra-luna-orchestrator:managed -->'
$transactionRoot = $null
$transactionChanges = @()
$transactionCommitted = $false
$transactionPreserved = $false
$managedBlockLines = @()
$componentSatisfied = $false
$legacySkillArchived = $false
$agentsInstructionsCanonical = $false
$banner = @'
+---------------------------------------+
|          CODEX ORCHESTRATOR            |
|       GPT-6 Astra/Sol/Luna profiles    |
|      with role-specific routing       |
+---------------------------------------+
'@

[Console]::WriteLine($banner)
[Console]::WriteLine('Interactive project setup for Windows')

function Read-Confirmation {
    param(
        [Parameter(Mandatory)]
        [string]$Prompt,

        [Parameter(Mandatory)]
        [bool]$DefaultYes
    )

    $suffix = if ($DefaultYes) { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        [Console]::Write("$Prompt $suffix ")
        $answer = [Console]::In.ReadLine()
        if ($null -eq $answer) {
            throw 'Input ended before setup was complete.'
        }

        switch ($answer.Trim().ToLowerInvariant()) {
            'y' { return $true }
            'yes' { return $true }
            'n' { return $false }
            'no' { return $false }
            '' { return $DefaultYes }
            default { [Console]::WriteLine('Please answer yes or no.') }
        }
    }
}

function Read-Plan {
    [Console]::WriteLine('Codex plan:')
    [Console]::WriteLine('  1) Pro  - Astra root; Luna defaults/explore/research; Sol worker/tester; Astra reviewer')
    [Console]::WriteLine('  2) Plus - Luna root (max); Luna defaults/roles; Astra reviewer')
    [Console]::WriteLine('  3) Pro (max 2 subagents)  - Pro topology with two concurrent subagent threads')
    [Console]::WriteLine('  4) Plus (max 2 subagents) - Plus topology with two concurrent subagent threads')

    while ($true) {
        [Console]::Write('Select plan [1-4] (default 1): ')
        $answer = [Console]::In.ReadLine()
        if ($null -eq $answer) {
            throw 'Input ended before setup was complete.'
        }

        switch ($answer.Trim().ToLowerInvariant()) {
            '1' { return 'pro' }
            'pro' { return 'pro' }
            '' { return 'pro' }
            '2' { return 'plus' }
            'plus' { return 'plus' }
            '3' { return 'pro-max-2-subagents' }
            'pro-max-2-subagents' { return 'pro-max-2-subagents' }
            '4' { return 'plus-max-2-subagents' }
            'plus-max-2-subagents' { return 'plus-max-2-subagents' }
            default { [Console]::WriteLine('Please answer 1 (Pro), 2 (Plus), 3 (Pro max 2), or 4 (Plus max 2).') }
        }
    }
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$Destination
    )

    foreach ($sourceChild in (Get-ChildItem -LiteralPath $Source -Force)) {
        $destinationChildPath = Join-Path $Destination $sourceChild.Name
        $destinationChild = Get-Item -LiteralPath $destinationChildPath -Force -ErrorAction SilentlyContinue

        if ($sourceChild.PSIsContainer) {
            if ($null -eq $destinationChild) {
                New-Item -ItemType Directory -Path $destinationChildPath | Out-Null
            }
            elseif (-not $destinationChild.PSIsContainer) {
                throw "Cannot merge directory over file: $destinationChildPath"
            }

            Copy-DirectoryContents -Source $sourceChild.FullName -Destination $destinationChildPath
        }
        else {
            if (($null -ne $destinationChild) -and $destinationChild.PSIsContainer) {
                throw "Cannot overwrite directory with file: $destinationChildPath"
            }

            Copy-Item -LiteralPath $sourceChild.FullName -Destination $destinationChildPath -Force | Out-Null
        }
    }
}

function Find-ReparsePoint {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    foreach ($child in (Get-ChildItem -LiteralPath $Path -Force)) {
        if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            return $child.FullName
        }
        if ($child.PSIsContainer) {
            $nestedLink = Find-ReparsePoint -Path $child.FullName
            if ($null -ne $nestedLink) {
                return $nestedLink
            }
        }
    }

    return $null
}

function Test-DirectoryMergeCompatible {
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$Destination
    )

    foreach ($sourceChild in (Get-ChildItem -LiteralPath $Source -Force)) {
        $destinationChildPath = Join-Path $Destination $sourceChild.Name
        $destinationChild = Get-Item -LiteralPath $destinationChildPath -Force -ErrorAction SilentlyContinue
        if ($null -eq $destinationChild) {
            continue
        }
        if ($sourceChild.PSIsContainer -ne $destinationChild.PSIsContainer) {
            return $false
        }
        if ($sourceChild.PSIsContainer -and (-not (Test-DirectoryMergeCompatible -Source $sourceChild.FullName -Destination $destinationChildPath))) {
            return $false
        }
    }

    return $true
}

function Get-ManagedBlockInfo {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]]$Lines
    )

    $beginIndexes = @()
    $endIndexes = @()
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if (($Lines[$index] -ceq $managedBegin) -or ($Lines[$index] -ceq $legacyManagedBegin)) {
            $beginIndexes += $index
        }
        if (($Lines[$index] -ceq $managedEnd) -or ($Lines[$index] -ceq $legacyManagedEnd)) {
            $endIndexes += $index
        }
    }

    if (($beginIndexes.Count -eq 0) -and ($endIndexes.Count -eq 0)) {
        return [pscustomobject]@{
            HasBlock    = $false
            IsMalformed = $false
            Block       = @()
        }
    }

    if (($beginIndexes.Count -ne 1) -or ($endIndexes.Count -ne 1) -or ($endIndexes[0] -le $beginIndexes[0])) {
        return [pscustomobject]@{
            HasBlock    = $false
            IsMalformed = $true
            Block       = @()
        }
    }

    $isCanonical = $Lines[$beginIndexes[0]] -ceq $managedBegin
    $expectedEnd = if ($isCanonical) { $managedEnd } else { $legacyManagedEnd }
    if ($Lines[$endIndexes[0]] -cne $expectedEnd) {
        return [pscustomobject]@{
            HasBlock    = $false
            IsMalformed = $true
            Block       = @()
        }
    }

    return [pscustomobject]@{
        HasBlock    = $true
        IsMalformed = $false
        Block       = [string[]]$Lines[$beginIndexes[0]..$endIndexes[0]]
        IsCanonical = $isCanonical
        BeginIndex  = $beginIndexes[0]
        EndIndex    = $endIndexes[0]
    }
}

function Test-Profile {
    param(
        [Parameter(Mandatory)]
        [string]$ProfileDirectory
    )

    $requiredPaths = @(
        'codex/config.toml',
        'codex/agents/explorer.toml',
        'codex/agents/researcher.toml',
        'codex/agents/reviewer.toml',
        'codex/agents/tester.toml',
        'codex/agents/worker.toml',
        'agents/skills/codex-orchestrator/SKILL.md'
    )

    foreach ($relativePath in $requiredPaths) {
        $path = Join-Path $ProfileDirectory $relativePath
        $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if (($null -eq $item) -or $item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Selected profile is incomplete: $path"
        }
    }

    $roleDirectory = Join-Path $ProfileDirectory 'codex/agents'
    $roleFiles = @(Get-ChildItem -LiteralPath $roleDirectory -File -Filter '*.toml' -Force)
    if ($roleFiles.Count -ne 5) {
        throw "Selected profile must contain exactly five role files: $roleDirectory"
    }
}

function Start-InstallTransaction {
    $rootName = 'codex-orchestrator-install-' + [Guid]::NewGuid().ToString('N')
    $script:transactionRoot = Join-Path ([IO.Path]::GetTempPath()) $rootName
    New-Item -ItemType Directory -Path $script:transactionRoot -Force | Out-Null

    $sourceAgentsPath = Join-Path $scriptDir 'AGENTS.md'
    $sourceLines = @([IO.File]::ReadAllLines($sourceAgentsPath))
    $sourceInfo = Get-ManagedBlockInfo -Lines $sourceLines
    if ($sourceInfo.IsMalformed -or (-not $sourceInfo.HasBlock) -or (-not $sourceInfo.IsCanonical)) {
        throw 'Setup source AGENTS.md has an invalid managed instruction block.'
    }

    $script:managedBlockLines = [string[]]$sourceInfo.Block
    $script:managedBlockPath = Join-Path $script:transactionRoot 'managed-block'
    [IO.File]::WriteAllLines($script:managedBlockPath, $script:managedBlockLines, [Text.UTF8Encoding]::new($false))
}

function Backup-InstallComponent {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$TargetDirectory
    )

    if ([string]::IsNullOrEmpty($script:transactionRoot)) {
        throw 'Installation transaction has not been started.'
    }

    $destinationPath = Join-Path $TargetDirectory $Name
    $destinationItem = Get-Item -LiteralPath $destinationPath -Force -ErrorAction SilentlyContinue
    $backupPath = $null
    $existing = $null -ne $destinationItem
    if ($existing) {
        if (($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to back up symbolic link or junction component: $Name"
        }
        $backupName = 'backup-' + ($Name.Replace('/', '_').Replace('\', '_'))
        $backupPath = Join-Path $script:transactionRoot $backupName
        Copy-Item -LiteralPath $destinationPath -Destination $backupPath -Recurse -Force | Out-Null
    }

    $change = [pscustomobject]@{
        Name       = $Name
        Existing   = $existing
        BackupPath = $backupPath
    }
    $script:transactionChanges = @($change) + @($script:transactionChanges)
}

function Restore-InstallTransaction {
    if ([string]::IsNullOrEmpty($script:transactionRoot) -or $script:transactionCommitted) {
        return
    }

    [Console]::Error.WriteLine('Setup failed; restoring the target to its previous state.')
    $restoreFailed = $false
    foreach ($change in @($script:transactionChanges)) {
        $destinationPath = Join-Path $targetDirectory $change.Name
        try {
            $destinationItem = Get-Item -LiteralPath $destinationPath -Force -ErrorAction SilentlyContinue
            if ($null -ne $destinationItem) {
                Remove-Item -LiteralPath $destinationPath -Recurse -Force -ErrorAction Stop
            }
            if ($change.Existing) {
                Copy-Item -LiteralPath $change.BackupPath -Destination $destinationPath -Recurse -Force | Out-Null
            }
        }
        catch {
            $restoreFailed = $true
            [Console]::Error.WriteLine("Warning: could not restore $($change.Name): $($_.Exception.Message)")
        }
    }
    if ($restoreFailed) {
        $script:transactionPreserved = $true
        [Console]::Error.WriteLine("Warning: rollback was incomplete; transaction backups were retained at $script:transactionRoot")
    }
}

function Clear-InstallTransaction {
    if (-not [string]::IsNullOrEmpty($script:transactionRoot)) {
        if ($script:transactionPreserved) {
            [Console]::Error.WriteLine("Transaction backups remain at $script:transactionRoot")
            return
        }
        try {
            Remove-Item -LiteralPath $script:transactionRoot -Recurse -Force -ErrorAction Stop
        }
        catch {
            $script:transactionPreserved = $true
            [Console]::Error.WriteLine("Warning: could not remove transaction backups; retained at $script:transactionRoot")
            return
        }
    }
    $script:transactionRoot = $null
    $script:managedBlockPath = $null
    $script:transactionChanges = @()
    $script:transactionPreserved = $false
}

function Write-TextLines {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]]$Lines,

        [string]$NewLine = [Environment]::NewLine
    )

    $text = [string]::Join($NewLine, $Lines) + $NewLine
    [IO.File]::WriteAllText($Path, $text, [Text.UTF8Encoding]::new($false))
}

function Update-ManagedAgents {
    param(
        [Parameter(Mandatory)]
        [string]$DestinationPath,

        [Parameter(Mandatory)]
        [string]$TargetDirectory
    )

    $currentLines = @([IO.File]::ReadAllLines($DestinationPath))
    $currentInfo = Get-ManagedBlockInfo -Lines $currentLines
    if ($currentInfo.IsMalformed) {
        throw 'Existing AGENTS.md has a malformed managed instruction block.'
    }

    if ($currentInfo.HasBlock) {
        $currentBlockText = [string]::Join("`n", [string[]]$currentInfo.Block)
        $managedBlockText = [string]::Join("`n", [string[]]$script:managedBlockLines)
        if ([string]::Equals($currentBlockText, $managedBlockText, [StringComparison]::Ordinal)) {
            [Console]::WriteLine('Skipped AGENTS.md: managed instructions are already up to date.')
            $script:componentSatisfied = $true
            return $false
        }

        [Console]::WriteLine('WARNING: AGENTS.md contains an older managed instruction block.')
        if (-not (Read-Confirmation -Prompt 'Update the managed instructions in AGENTS.md?' -DefaultYes $false)) {
            [Console]::WriteLine('Skipped AGENTS.md (existing managed instructions left unchanged).')
            return $false
        }

        Backup-InstallComponent -Name 'AGENTS.md' -TargetDirectory $TargetDirectory
        $updatedLines = New-Object 'System.Collections.Generic.List[string]'
        for ($index = 0; $index -lt $currentLines.Count; $index++) {
            if ($index -eq $currentInfo.BeginIndex) {
                foreach ($line in @($script:managedBlockLines)) {
                    $updatedLines.Add($line)
                }
                $index = $currentInfo.EndIndex
                continue
            }
            $updatedLines.Add($currentLines[$index])
        }
        $newLine = if ([IO.File]::ReadAllText($DestinationPath).Contains("`r`n")) { "`r`n" } else { "`n" }
        Write-TextLines -Path $DestinationPath -Lines $updatedLines.ToArray() -NewLine $newLine
        [Console]::WriteLine('Updated the managed instructions in AGENTS.md.')
        $script:componentSatisfied = $true
        return $true
    }

    [Console]::WriteLine('WARNING: existing AGENTS.md has no managed instruction block; setup will append one.')
    if (-not (Read-Confirmation -Prompt 'Add the managed instructions to AGENTS.md?' -DefaultYes $false)) {
        [Console]::WriteLine('Skipped AGENTS.md (existing contents left unchanged).')
        return $false
    }

    Backup-InstallComponent -Name 'AGENTS.md' -TargetDirectory $TargetDirectory
    $existingText = [IO.File]::ReadAllText($DestinationPath).Replace("`r`n", "`n").Replace("`r", "`n")
    $blockText = [string]::Join("`n", [string[]]$script:managedBlockLines)
    if ($existingText.Length -eq 0) {
        $updatedText = $blockText + "`n"
    }
    elseif ($existingText.EndsWith("`n")) {
        $updatedText = $existingText + "`n" + $blockText + "`n"
    }
    else {
        $updatedText = $existingText + "`n`n" + $blockText + "`n"
    }
    [IO.File]::WriteAllText($DestinationPath, $updatedText, [Text.UTF8Encoding]::new($false))
    [Console]::WriteLine('Appended managed instructions to AGENTS.md. Existing contents preserved.')
    $script:componentSatisfied = $true
    return $true
}

function Get-OverwritePaths {
    param(
        [Parameter(Mandatory)]
        [System.IO.FileSystemInfo]$Source,

        [Parameter(Mandatory)]
        [string]$Destination,

        [Parameter(Mandatory)]
        [string]$Name
    )

    if (-not $Source.PSIsContainer) {
        if ($null -ne (Get-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue)) {
            return $Name
        }
        return
    }

    foreach ($sourceFile in (Get-ChildItem -LiteralPath $Source.FullName -File -Recurse -Force)) {
        $relativePath = $sourceFile.FullName.Substring($Source.FullName.Length + 1)
        $destinationFile = Join-Path $Destination $relativePath
        if ($null -ne (Get-Item -LiteralPath $destinationFile -Force -ErrorAction SilentlyContinue)) {
            $path = $Name + [IO.Path]::DirectorySeparatorChar + $relativePath
            Write-Output $path
        }
    }
}

function Show-OverwriteWarning {
    param(
        [Parameter(Mandatory)]
        [System.IO.FileSystemInfo]$Source,

        [Parameter(Mandatory)]
        [string]$Destination,

        [Parameter(Mandatory)]
        [string]$Name
    )

    $paths = @(Get-OverwritePaths -Source $Source -Destination $Destination -Name $Name)
    if ($paths.Count -eq 0) {
        return
    }

    [Console]::WriteLine('WARNING: the following existing files will be overwritten:')
    foreach ($path in $paths) {
        [Console]::WriteLine("  - $path")
    }
}

function Get-LegacySkillArchivePath {
    param(
        [Parameter(Mandatory)]
        [string]$AgentsDirectory
    )

    $legacyPath = Join-Path $AgentsDirectory 'skills/astra-orchestrator'
    $legacyItem = Get-Item -LiteralPath $legacyPath -Force -ErrorAction SilentlyContinue
    if ($null -eq $legacyItem) {
        return $null
    }
    if (-not $legacyItem.PSIsContainer) {
        throw "Legacy skill path must be a directory: $legacyPath"
    }

    $backupDirectory = Join-Path $AgentsDirectory 'migration-backups'
    $backupItem = Get-Item -LiteralPath $backupDirectory -Force -ErrorAction SilentlyContinue
    if (($null -ne $backupItem) -and (-not $backupItem.PSIsContainer)) {
        throw "Legacy skill backup path must be a directory: $backupDirectory"
    }
    $basePath = Join-Path $backupDirectory 'astra-orchestrator'
    $archivePath = $basePath
    $suffix = 0
    while ($null -ne (Get-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue)) {
        $suffix++
        $archivePath = "$basePath.$suffix"
    }
    return $archivePath
}

function Install-Component {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$TargetDirectory,

        [string]$SourcePath
    )

    if ([string]::IsNullOrEmpty($SourcePath)) {
        $SourcePath = Join-Path $scriptDir $Name
    }
    $script:componentSatisfied = $false
    $sourcePath = $SourcePath
    $destinationPath = Join-Path $TargetDirectory $Name
    $sourceItem = Get-Item -LiteralPath $sourcePath -Force -ErrorAction SilentlyContinue
    if ($null -eq $sourceItem) {
        throw "Setup source is missing: $sourcePath"
    }
    if (($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Setup source must not be a symbolic link or junction: $sourcePath"
    }

    $destinationItem = Get-Item -LiteralPath $destinationPath -Force -ErrorAction SilentlyContinue
    if ($null -ne $destinationItem) {
        if (($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            [Console]::Error.WriteLine("Skipped ${Name}: the existing target is a symbolic link or junction.")
            return $false
        }

        if ($Name -eq 'AGENTS.md') {
            if ($destinationItem.PSIsContainer) {
                [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
                return $false
            }
            return Update-ManagedAgents -DestinationPath $destinationPath -TargetDirectory $TargetDirectory
        }

        if ($sourceItem.PSIsContainer -and $destinationItem.PSIsContainer) {
            $linkedPath = Find-ReparsePoint -Path $destinationPath
            if ($null -ne $linkedPath) {
                [Console]::Error.WriteLine("Skipped ${Name}: the existing target contains a symbolic link or junction ($linkedPath).")
                return $false
            }
            if (-not (Test-DirectoryMergeCompatible -Source $sourcePath -Destination $destinationPath)) {
                [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
                return $false
            }
        }
        elseif (($sourceItem.PSIsContainer -and (-not $destinationItem.PSIsContainer)) -or ((-not $sourceItem.PSIsContainer) -and $destinationItem.PSIsContainer)) {
            [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
            return $false
        }

        Show-OverwriteWarning -Source $sourceItem -Destination $destinationPath -Name $Name

        $archivePath = $null
        if ($Name -eq '.agents') {
            $archivePath = Get-LegacySkillArchivePath -AgentsDirectory $destinationPath
            if ($null -ne $archivePath) {
                [Console]::WriteLine("Legacy skill will be moved from $(Join-Path $destinationPath 'skills/astra-orchestrator') to $archivePath.")
            }
        }

        $updatePrompt = "Update ${Name}? New files will be added; only paths listed above will be replaced."
        if ($null -ne $archivePath) {
            $updatePrompt += ' The legacy skill will be archived at the path listed above.'
        }
        if (-not (Read-Confirmation -Prompt $updatePrompt -DefaultYes $false)) {
            [Console]::WriteLine("Skipped $Name (existing target left unchanged).")
            return $false
        }

        Backup-InstallComponent -Name $Name -TargetDirectory $TargetDirectory
        if ($null -ne $archivePath) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $archivePath) -Force | Out-Null
            if ($null -ne (Get-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue)) {
                throw "Migration archive destination appeared during setup: $archivePath"
            }
            Move-Item -LiteralPath (Join-Path $destinationPath 'skills/astra-orchestrator') -Destination $archivePath | Out-Null
            $script:legacySkillArchived = $true
            [Console]::WriteLine("Archived legacy skill to $archivePath.")
        }
        if ($sourceItem.PSIsContainer -and $destinationItem.PSIsContainer) {
            Copy-DirectoryContents -Source $sourcePath -Destination $destinationPath
        }
        elseif ((-not $sourceItem.PSIsContainer) -and (-not $destinationItem.PSIsContainer)) {
            Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force | Out-Null
        }
        else {
            [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
            return $false
        }

        [Console]::WriteLine("Updated $Name.")
        $script:componentSatisfied = $true
        return $true
    }

    Backup-InstallComponent -Name $Name -TargetDirectory $TargetDirectory
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force | Out-Null
    [Console]::WriteLine("Installed $Name.")
    $script:componentSatisfied = $true
    return $true
}

try {
    [Console]::Write('Target repository path: ')
    $targetPath = [Console]::In.ReadLine()
    if ($null -eq $targetPath) {
        throw 'Input ended before a target repository was provided.'
    }
    if ([string]::IsNullOrWhiteSpace($targetPath)) {
        throw 'Target repository path cannot be empty.'
    }

    $targetItem = Get-Item -LiteralPath $targetPath -Force -ErrorAction SilentlyContinue
    if (($null -eq $targetItem) -or (-not $targetItem.PSIsContainer)) {
        throw "Target must be an existing directory: $targetPath"
    }

    $targetDirectory = $targetItem.FullName
    if ([string]::Equals($targetDirectory, $scriptDir, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Target repository must be different from the setup source directory.'
    }

    $plan = Read-Plan
    $profileDirectory = Join-Path $scriptDir "profiles/$plan"
    Test-Profile -ProfileDirectory $profileDirectory
    Start-InstallTransaction

    $installed = 0
    $satisfied = 0
    foreach ($component in '.codex', '.agents', 'AGENTS.md') {
        $script:componentSatisfied = $false
        if (Read-Confirmation -Prompt "Install ${component}?" -DefaultYes $true) {
            $result = if ($component -eq '.codex') {
                Install-Component -Name $component -TargetDirectory $targetDirectory -SourcePath (Join-Path $profileDirectory "codex")
            }
            elseif ($component -eq '.agents') {
                Install-Component -Name $component -TargetDirectory $targetDirectory -SourcePath (Join-Path $profileDirectory "agents")
            }
            else {
                Install-Component -Name $component -TargetDirectory $targetDirectory
            }
            if ($result) {
                $installed++
            }
            if ($script:componentSatisfied) {
                $satisfied++
                if ($component -eq 'AGENTS.md') {
                    $agentsInstructionsCanonical = $true
                }
            }
        }
        else {
            [Console]::WriteLine("Skipped $component.")
        }
    }

    $script:transactionCommitted = $true
    if ($script:legacySkillArchived -and (-not $agentsInstructionsCanonical)) {
        [Console]::Error.WriteLine('WARNING: the legacy skill was archived, but AGENTS.md may still reference astra-orchestrator. Approve the AGENTS.md update or edit those references, then rerun setup.')
    }
    if ($agentsInstructionsCanonical -and (-not (Test-Path -LiteralPath (Join-Path $targetDirectory '.agents/skills/codex-orchestrator/SKILL.md') -PathType Leaf))) {
        [Console]::Error.WriteLine('WARNING: AGENTS.md now invokes codex-orchestrator, but the canonical skill is missing because .agents was skipped or declined. Approve the .agents update, then rerun setup.')
    }
    if ($satisfied -lt 3) {
        [Console]::Error.WriteLine("WARNING: partial installation completed ($satisfied of 3 components satisfied).")
    }
    [Console]::WriteLine()
    [Console]::WriteLine("Setup complete. $installed component(s) installed in $targetDirectory (plan: $plan).")
    [Console]::WriteLine('See guides/ for optional Codex model and Fast-mode configurations.')
}
catch {
    Restore-InstallTransaction
    [Console]::Error.WriteLine("Setup cancelled: $($_.Exception.Message)")
    exit 1
}
finally {
    Clear-InstallTransaction
}
