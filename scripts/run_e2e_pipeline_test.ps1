param(
    [string]$BookPath = "",
    [string]$Voice = "M3",
    [switch]$KeepGeneratedBook,
    [switch]$UseGpu,
    [switch]$SkipExtraction,
    [switch]$SkipWhisperX,
    [int]$TextChapters = 6,
    [switch]$TenWords,
    [string]$GeneratedBookName = "cadence_e2e_short_book"
)

$ErrorActionPreference = "Stop"

function New-ShortEpub {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [string]$Title = "Cadence E2E Short Book",
        [string]$Author = "Cadence Test"
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $tmpRoot = Join-Path $env:TEMP ("cadence-e2e-" + [Guid]::NewGuid().ToString("N"))
    $null = New-Item -ItemType Directory -Path $tmpRoot

    try {
        $mimetypePath = Join-Path $tmpRoot "mimetype"
        Set-Content -Path $mimetypePath -Value "application/epub+zip" -NoNewline -Encoding ascii

        $metaInf = Join-Path $tmpRoot "META-INF"
        $oebps = Join-Path $tmpRoot "OEBPS"
        $null = New-Item -ItemType Directory -Path $metaInf
        $null = New-Item -ItemType Directory -Path $oebps

        @"
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"@ | Set-Content -Path (Join-Path $metaInf "container.xml") -Encoding utf8

        @"
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>$Title</dc:title>
    <dc:creator>$Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="BookId">urn:uuid:$([Guid]::NewGuid().ToString())</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>
"@ | Set-Content -Path (Join-Path $oebps "content.opf") -Encoding utf8

        @"
<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:$([Guid]::NewGuid().ToString())"/>
  </head>
  <docTitle><text>$Title</text></docTitle>
  <navMap>
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="ch1.xhtml"/>
    </navPoint>
    <navPoint id="navPoint-2" playOrder="2">
      <navLabel><text>Chapter 2</text></navLabel>
      <content src="ch2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"@ | Set-Content -Path (Join-Path $oebps "toc.ncx") -Encoding utf8

        @"
<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 1</title></head>
  <body>
    <h1>Chapter 1</h1>
    <p>This is a short generated chapter for Cadence end to end testing.</p>
    <p>We test extraction, synthesis, and alignment as one pipeline.</p>
  </body>
</html>
"@ | Set-Content -Path (Join-Path $oebps "ch1.xhtml") -Encoding utf8

        @"
<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 2</title></head>
  <body>
    <h1>Chapter 2</h1>
    <p>The second chapter keeps this book tiny while still testing multi chapter flow.</p>
    <p>Cadence should produce wav and json outputs for each chapter.</p>
  </body>
</html>
"@ | Set-Content -Path (Join-Path $oebps "ch2.xhtml") -Encoding utf8

        if (Test-Path $OutputPath) {
            Remove-Item -Path $OutputPath -Force
        }

        $zip = [System.IO.Compression.ZipFile]::Open($OutputPath, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            # EPUB requires mimetype first and uncompressed.
            $mimeEntry = $zip.CreateEntry("mimetype", [System.IO.Compression.CompressionLevel]::NoCompression)
            $mimeStream = $mimeEntry.Open()
            try {
                $mimeBytes = [System.Text.Encoding]::ASCII.GetBytes("application/epub+zip")
                $mimeStream.Write($mimeBytes, 0, $mimeBytes.Length)
            } finally {
                $mimeStream.Dispose()
            }

            $files = Get-ChildItem -Path $tmpRoot -Recurse -File | Where-Object { $_.Name -ne "mimetype" }
            foreach ($file in $files) {
                $relative = $file.FullName.Substring($tmpRoot.Length + 1).Replace("\\", "/")
                $entry = $zip.CreateEntry($relative, [System.IO.Compression.CompressionLevel]::Optimal)
                $entryStream = $entry.Open()
                try {
                    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
                    $entryStream.Write($bytes, 0, $bytes.Length)
                } finally {
                    $entryStream.Dispose()
                }
            }
        } finally {
            $zip.Dispose()
        }
    }
    finally {
        if (Test-Path $tmpRoot) {
            Remove-Item -Path $tmpRoot -Recurse -Force
        }
    }
}

$generated = $false
$resolvedBook = $BookPath

if ([string]::IsNullOrWhiteSpace($resolvedBook)) {
    $resolvedBook = Join-Path $PSScriptRoot "$GeneratedBookName.epub"
    Write-Host "Generating short EPUB: $resolvedBook"
    New-ShortEpub -OutputPath $resolvedBook
    $generated = $true
}

if (-not (Test-Path $resolvedBook)) {
    throw "Book not found: $resolvedBook"
}

Write-Host "Running real e2e pipeline test with: $resolvedBook"

$env:CADENCE_RUN_E2E = "1"
$env:CADENCE_E2E_BOOK = (Resolve-Path $resolvedBook).Path
$env:CADENCE_E2E_VOICE = $Voice
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
if ($SkipExtraction) {
    $env:CADENCE_E2E_SKIP_EXTRACTION = "1"
    $env:CADENCE_E2E_TEXT_CHAPTERS = [string]([Math]::Max(1, $TextChapters))
    if ($TenWords) {
        $env:CADENCE_E2E_TEXT_TEMPLATE = "Quick benchmark line to validate synthesis and alignment path now."
    } else {
        Remove-Item Env:CADENCE_E2E_TEXT_TEMPLATE -ErrorAction SilentlyContinue
    }
    Write-Host "E2E mode: text-only (skip extraction), chapters=$($env:CADENCE_E2E_TEXT_CHAPTERS)"
} else {
    Remove-Item Env:CADENCE_E2E_SKIP_EXTRACTION -ErrorAction SilentlyContinue
    Remove-Item Env:CADENCE_E2E_TEXT_CHAPTERS -ErrorAction SilentlyContinue
    Remove-Item Env:CADENCE_E2E_TEXT_TEMPLATE -ErrorAction SilentlyContinue
}

if ($SkipWhisperX) {
    $env:CADENCE_E2E_SKIP_WHISPERX = "1"
    Write-Host "E2E mode: skipping WhisperX (generation-only benchmark)"
} else {
    Remove-Item Env:CADENCE_E2E_SKIP_WHISPERX -ErrorAction SilentlyContinue
}

if ($UseGpu) {
    Write-Host "E2E mode: GPU"
    $env:CADENCE_FORCE_CPU = "0"
    $env:CADENCE_CUDA_ONLY = "1"
    $env:CADENCE_USE_TENSORRT = "0"
    $env:CADENCE_WHISPERX_DEVICE = "cuda"
    $env:CADENCE_WHISPERX_COMPUTE_TYPE = "float16"
} else {
    Write-Host "E2E mode: CPU-safe"
    $env:CADENCE_FORCE_CPU = "1"
    $env:CADENCE_CUDA_ONLY = "0"
    $env:CADENCE_USE_TENSORRT = "0"
    $env:CADENCE_ADD_SYSTEM_CUDA_DLL_PATH = "0"
    $env:CADENCE_WHISPERX_DEVICE = "cpu"
    $env:CADENCE_WHISPERX_COMPUTE_TYPE = "int8"
}

# Ensure ONNX Runtime package set is sane for selected mode.
python.exe -c "import importlib.metadata as m; p={d.metadata['Name'].lower() for d in m.distributions() if d.metadata.get('Name')}; print('onnx pkgs:', sorted([x for x in p if x in {'onnxruntime','onnxruntime-gpu'}]))"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect installed ONNX Runtime packages."
}

if ($UseGpu) {
    python.exe -c "import importlib.metadata as m; p={d.metadata['Name'].lower() for d in m.distributions() if d.metadata.get('Name')}; raise SystemExit(1 if ('onnxruntime' in p and 'onnxruntime-gpu' in p) else 0)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "GPU mode requires a single ONNX Runtime package."
        Write-Host "Detected both 'onnxruntime' and 'onnxruntime-gpu'."
        Write-Host "Fix with:"
        Write-Host "  pip uninstall -y onnxruntime onnxruntime-gpu"
        Write-Host "  pip install onnxruntime-gpu==1.24.1"
        exit 1
    }
}

# Preflight ONNX Runtime import so failures are clear before pytest starts.
python.exe -c "import onnxruntime as ort; print('onnxruntime providers:', ort.get_available_providers())"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ONNX Runtime failed to import in this venv."
    Write-Host "Try one of these fixes:"
    Write-Host "  1) CPU path (recommended for E2E stability):"
    Write-Host "     pip uninstall -y onnxruntime-gpu"
    Write-Host "     pip install onnxruntime"
    Write-Host "  2) GPU path: install matching CUDA/cuDNN runtime for your onnxruntime-gpu wheel."
    exit $LASTEXITCODE
}

python.exe -m pytest -q -m e2e tests\e2e\test_full_pipeline_real.py -s
$exitCode = $LASTEXITCODE

if ($generated -and -not $KeepGeneratedBook -and (Test-Path $resolvedBook)) {
    Remove-Item -Path $resolvedBook -Force
}

exit $exitCode
