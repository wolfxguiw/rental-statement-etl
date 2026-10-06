$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$distPath = Join-Path $projectRoot "dist"
$workPath = Join-Path $projectRoot "build\pyinstaller"
$ocrExecutable = Join-Path $projectRoot "vendor\tesseract\tesseract.exe"
$portugueseData = Join-Path $projectRoot "vendor\tesseract\tessdata\por.traineddata"
$ocrManifest = Join-Path $projectRoot "vendor\tesseract\SHA256SUMS.txt"
$notices = Join-Path $projectRoot "THIRD_PARTY_NOTICES.txt"

if (-not (Test-Path -LiteralPath $ocrExecutable)) {
    throw "O OCR local do Tesseract não foi encontrado em vendor\tesseract."
}
if (-not (Test-Path -LiteralPath $portugueseData)) {
    throw "O modelo de português do OCR não foi encontrado em vendor\tesseract\tessdata."
}
if (-not (Test-Path -LiteralPath $ocrManifest)) {
    throw "O manifesto SHA-256 dos recursos OCR está ausente."
}
if (-not (Test-Path -LiteralPath $notices)) {
    throw "O arquivo THIRD_PARTY_NOTICES.txt é necessário para a distribuição."
}

$manifestRoot = Join-Path $projectRoot "vendor\tesseract"
$manifestRootPrefix = [System.IO.Path]::GetFullPath($manifestRoot).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
$manifestEntries = @{}
foreach ($line in Get-Content -LiteralPath $ocrManifest) {
    if ($line -notmatch '^(?<hash>[0-9a-fA-F]{64})  (?<relative>.+)$') {
        throw "Linha inválida em vendor\tesseract\SHA256SUMS.txt."
    }
    $manifestEntries[$Matches.relative] = $Matches.hash.ToUpperInvariant()
}
$ocrFiles = @(Get-ChildItem -LiteralPath $manifestRoot -Recurse -File | Where-Object {
    $_.FullName -ne $ocrManifest
})
if ($ocrFiles.Count -ne $manifestEntries.Count) {
    throw "Os arquivos OCR não correspondem ao manifesto SHA-256."
}
foreach ($file in $ocrFiles) {
    $relative = [System.IO.Path]::GetFullPath($file.FullName).Substring($manifestRootPrefix.Length).Replace('\', '/')
    if (-not $manifestEntries.ContainsKey($relative)) {
        throw "Arquivo OCR sem hash no manifesto: $relative"
    }
    $actualHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    if ($actualHash -ne $manifestEntries[$relative]) {
        throw "Hash de recurso OCR divergente: $relative"
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Instale Python 3.12 para desenvolvimento; o comando 'py -3.12' não foi encontrado."
    }
    & py -3.12 -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar o ambiente virtual de build." }
}

Push-Location $projectRoot
try {
    & $venvPython -m pip install --disable-pip-version-check --no-input -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências fixadas do build." }

    & $venvPython -m PyInstaller --noconfirm --clean `
        --distpath $distPath `
        --workpath $workPath `
        (Join-Path $projectRoot "ExtratorAlugueis.spec")
    if ($LASTEXITCODE -ne 0) { throw "O build do ExtratorAlugueis falhou." }

    $releaseExe = Join-Path $distPath "ExtratorAlugueis\ExtratorAlugueis.exe"
    if (-not (Test-Path -LiteralPath $releaseExe)) {
        throw "O build terminou sem criar $releaseExe."
    }
    $releaseDir = Split-Path -Parent $releaseExe
    $releaseOcr = Join-Path $releaseDir "_internal\ocr"
    if (-not (Test-Path -LiteralPath (Join-Path $releaseOcr "tesseract.exe")) -or
        -not (Test-Path -LiteralPath (Join-Path $releaseOcr "tessdata\por.traineddata"))) {
        throw "A distribuição não contém o executável e os dados de OCR locais."
    }
    Copy-Item -LiteralPath $notices -Destination $releaseDir -Force

    $artifactDir = Join-Path $projectRoot "artifacts"
    New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
    $archivePath = Join-Path $artifactDir "ExtratorAlugueis_Windows_0.2.4.zip"
    Compress-Archive -Path $releaseDir -DestinationPath $archivePath -CompressionLevel Optimal -Force
    Write-Host "Release criada em: $releaseDir"
    Write-Host "Pacote ZIP criado em: $archivePath"
}
finally {
    Pop-Location
}
