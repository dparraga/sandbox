# Provision upstream OCR assets locally. No installer, registry change or application processing.
param([string]$Destination = 'reports/ocr-assets')
$ErrorActionPreference = 'Stop'
$assetRoot = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $assetRoot | Out-Null
function Get-VerifiedAsset([string]$Url, [string]$Path, [long]$Bytes, [string]$Hash) {
    if (-not (Test-Path -LiteralPath $Path)) {
        $partial = $Path + '.part'
        try {
            Invoke-WebRequest -Uri $Url -OutFile $partial -TimeoutSec 120 -UseBasicParsing
            if ((Get-Item -LiteralPath $partial).Length -ne $Bytes -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) { throw 'Downloaded asset identity mismatch' }
            Move-Item -LiteralPath $partial -Destination $Path
        } finally { if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial } }
    }
    if ((Get-Item -LiteralPath $Path).Length -ne $Bytes -or (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) { throw 'Cached asset identity mismatch' }
}
$tools = Join-Path $assetRoot 'tools'
$model = Join-Path $assetRoot 'models'
$engine = Join-Path $assetRoot 'engine'
New-Item -ItemType Directory -Force -Path $tools,$model,$engine | Out-Null
$archive = Join-Path $tools '7z2605-x64.exe'
Get-VerifiedAsset 'https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.exe' $archive 1663506 'fd99e86f57d8f429ef5ed045bf98315af962e2309b0f1ba87a147a44c71647d0'
# Windows tar opens this verified 7-Zip SFX. Extract only the portable tool and its notices.
& "$env:SystemRoot\System32\tar.exe" -xf $archive -C $tools '7z.exe' '7z.dll' 'License.txt' 'readme.txt'
if ($LASTEXITCODE -ne 0) { throw 'Portable archive-tool extraction failed' }
$installer = Join-Path $assetRoot 'tesseract-ocr-w64-setup-5.5.3.20260724.exe'
Get-VerifiedAsset 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe' $installer 26573224 'bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4'
& (Join-Path $tools '7z.exe') x $installer "-o$engine" 'tesseract.exe' '*.dll' 'doc/*' -r -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'OCR payload extraction failed' }
$executable = Join-Path $engine 'tesseract.exe'
$engineHash = 'c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420'
if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -ne $engineHash) { throw 'Extracted OCR engine identity mismatch' }
Get-VerifiedAsset 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/65727574dfcd264acbb0c3e07860e4e9e9b22185/eng.traineddata' (Join-Path $model 'eng.traineddata') 4113088 '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
$manifest = [ordered]@{tesseract_executable=$executable; tessdata_directory=$model; executable_sha256=$engineHash; model_sha256='7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'; source='upstream verified downloads; not a redistributed bundle'}
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $assetRoot 'assets.json')
$manifest | ConvertTo-Json
