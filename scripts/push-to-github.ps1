<#
.SYNOPSIS
    Initialise the repository and push it to GitHub.

.DESCRIPTION
    Run once from the project root. If the GitHub CLI (gh) is installed and
    authenticated, the remote repository is created for you. Otherwise create
    an EMPTY repository on github.com first (no README, no .gitignore, no
    licence) and pass its URL with -RemoteUrl.

    This file is deliberately pure ASCII. Windows PowerShell 5.1 reads a
    BOM-less script as Windows-1252, and a UTF-8 em dash decodes into a smart
    quote that PowerShell treats as a real string delimiter.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\push-to-github.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\push-to-github.ps1 -RemoteUrl https://github.com/USERNAME/aivoa-complaint-intelligence.git
#>
[CmdletBinding()]
param(
    [string] $RepoName    = 'aivoa-complaint-intelligence',
    [string] $RemoteUrl   = '',
    [ValidateSet('public', 'private')]
    [string] $Visibility  = 'public',
    [string] $Description = 'AI-assisted customer complaint intake and triage for GMP-regulated pharmaceutical manufacturing. FastAPI + LangGraph + Groq + React/Redux.'
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

function Step($msg) { Write-Host ''; Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# Under $ErrorActionPreference = 'Stop', Windows PowerShell 5.1 can turn a
# native (external) command's own failure - stderr text, or just a non-zero
# exit code - into a terminating exception, even when that output is being
# redirected or piped to Out-Null. It does this no matter how the streams are
# redirected, because the conversion happens as the native command's own
# output is captured, before the redirect operator gets a say. The reliable
# fix is to relax ErrorActionPreference for the duration of the call and
# decide what to do afterwards by reading $LASTEXITCODE, same as in cmd.exe.
function Invoke-Native {
    param([Parameter(Mandatory)][scriptblock] $Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Route the wrapped command's own output through Out-Host rather than
        # letting it fall through this function's own output stream. Without
        # this, PowerShell bundles that output together with the explicit
        # `return $LASTEXITCODE` below into a single array, so a caller
        # doing `if ($exit -ne 0)` is comparing an array (always -ne 0 in a
        # way that reads as truthy garbage) instead of a clean integer - the
        # exact bug that turned a successful `git push` into a false-positive
        # "git push failed (exit code ...)" error.
        & $Command | Out-Host
    } finally {
        $ErrorActionPreference = $previous
    }
    return $LASTEXITCODE
}

# ---- Preconditions ---------------------------------------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git is not installed or not on PATH. Install it from https://git-scm.com/download/win'
}
if (-not (Test-Path 'README.md') -or -not (Test-Path 'backend')) {
    throw "This does not look like the AIVOA project root ($(Get-Location))."
}

# git refuses to commit without an identity, and its error is not obvious the
# first time you meet it. Ask once, store globally.
if (-not (git config --global user.name)) {
    Warn 'git has no global user.name configured.'
    $gitName = Read-Host '    Your name (for commit authorship)'
    git config --global user.name $gitName
}
if (-not (git config --global user.email)) {
    Warn 'git has no global user.email configured.'
    $gitEmail = Read-Host '    Your GitHub e-mail address'
    git config --global user.email $gitEmail
}
Ok ("Committing as " + (git config --global user.name) + " <" + (git config --global user.email) + ">")

# A stray .env would publish your Groq key. .gitignore covers it; say so anyway.
foreach ($envFile in @('.env', 'backend\.env', 'frontend\.env', 'frontend\.env.local')) {
    if (Test-Path $envFile) {
        Warn "$envFile exists locally - .gitignore keeps it out of the commit."
    }
}

# ---- Repository ------------------------------------------------------------
Step 'Preparing the local repository'
if (-not (Test-Path '.git')) {
    git init | Out-Null
    Ok 'Initialised a new repository.'
} else {
    Ok 'Repository already initialised.'
}

git add -A
$staged = @(git diff --cached --name-only)
if ($staged.Count -gt 0) {
    $subject = 'AIVOA complaint intelligence: LangGraph intake agent, FastAPI backend, React/Redux UI'
    $body = @(
        'AI-assisted customer complaint intake and triage for GMP-regulated API and finished-dosage-form manufacturing.',
        '- LangGraph pipeline: conditional routing, fan-out/fan-in, per-node trace streamed over SSE and persisted for audit',
        '- Groq gemma2-9b-it for extraction, llama-3.3-70b-versatile for reasoning, with a deterministic engine that keeps the product working without a key',
        '- Field-level provenance: every extracted value carries confidence, source and the verbatim evidence it came from',
        '- Deterministic safety floor the model cannot lower on patient-safety signals',
        '- Explainable duplicate detection, completeness checking against 21 CFR 211.198(a), root-cause hypotheses and CAPA recommendations',
        '- React 18 + Redux Toolkit, bespoke design system, 43 backend tests'
    )
    $gitArgs = @('commit', '-m', $subject)
    foreach ($line in $body) { $gitArgs += '-m'; $gitArgs += $line }
    & git @gitArgs | Out-Null
    Ok ("Committed " + $staged.Count + " file(s).")
} else {
    Ok 'Nothing new to commit.'
}

git branch -M main
Ok 'Branch set to main.'

# ---- Remote ----------------------------------------------------------------
Step 'Configuring the remote'
# Deliberately NOT `git remote get-url origin 2>$null`: git writes to stderr
# when the remote is absent, and with $ErrorActionPreference = 'Stop' a
# *redirected* native stderr stream becomes a terminating error. Listing the
# remotes is silent and exits 0 when there are none.
$existingRemote = $null
if (@(git remote) -contains 'origin') {
    $existingRemote = git remote get-url origin
}

if ($RemoteUrl) {
    if ($existingRemote) { git remote set-url origin $RemoteUrl } else { git remote add origin $RemoteUrl }
    Ok "origin -> $RemoteUrl"
}
elseif ($existingRemote) {
    Ok "origin already set -> $existingRemote"
}
elseif (Get-Command gh -ErrorAction SilentlyContinue) {
    $authExit = Invoke-Native { gh auth status 2>&1 | Out-Null }
    if ($authExit -ne 0) {
        Warn 'The GitHub CLI is installed but not signed in. Running gh auth login ...'
        $loginExit = Invoke-Native { gh auth login }
        if ($loginExit -ne 0) {
            throw 'gh auth login did not finish successfully. Re-run this script after signing in.'
        }
        Ok 'Signed in.'
    } else {
        Ok 'GitHub CLI already signed in.'
    }

    Step "Creating the GitHub repository ($Visibility)"
    $createExit = Invoke-Native { gh repo create $RepoName "--$Visibility" --source=. --remote=origin --description $Description }
    if ($createExit -ne 0) {
        throw "gh repo create failed (exit code $createExit). See the output above - a repository named '$RepoName' may already exist on your account."
    }
    Ok "Created and linked $RepoName."
}
else {
    Warn ''
    Warn 'No remote configured and the GitHub CLI is not installed.'
    Warn ''
    Warn 'Option A - install the GitHub CLI, then re-run this script:'
    Warn '    winget install --id GitHub.cli'
    Warn '    gh auth login'
    Warn ''
    Warn 'Option B - create an EMPTY repository at https://github.com/new'
    Warn '(no README, no .gitignore, no licence), then re-run with its URL:'
    Warn ("    powershell -ExecutionPolicy Bypass -File scripts\push-to-github.ps1 -RemoteUrl https://github.com/USERNAME/" + $RepoName + ".git")
    Warn ''
    exit 1
}

# ---- Push ------------------------------------------------------------------
Step 'Pushing to GitHub'
$pushExit = Invoke-Native { git push -u origin main }
if ($pushExit -ne 0) {
    throw "git push failed (exit code $pushExit). See the error above - a common cause is that the GitHub repository already has commits (for example a README added on the website) that your local history does not have. If so, run 'git pull --rebase origin main' once and then re-run this script."
}
Ok 'Pushed to origin/main.'

$url = (git remote get-url origin) -replace '\.git$', ''
Write-Host ''
Write-Host "    Done. $url" -ForegroundColor Green
Write-Host ''
