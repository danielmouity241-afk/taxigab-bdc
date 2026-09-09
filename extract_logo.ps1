param(
    [string]$PdfPath = "C:\Users\hp\Downloads\logo taxi gab+ (1).pdf",
    [string]$OutPng = "C:\Users\hp\.gemini\antigravity\scratch\taxigab-bdc\static\images\logo_taxigab.png"
)

Add-Type -AssemblyName System.Drawing
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null

$outDir = Split-Path $OutPng
if (!(Test-Path $outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

$asyncFile = [Windows.Storage.StorageFile]::GetFileFromPathAsync($PdfPath)
$file = $asyncFile.AsTask().Result

$asyncDoc = [Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)
$pdfDoc = $asyncDoc.AsTask().Result

$page = $pdfDoc.GetPage(0)

# Save to temporary file using storage file or stream
$tempPng = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "temp_logo.png")
$asyncTemp = [Windows.Storage.StorageFolder]::GetFolderFromPathAsync([System.IO.Path]::GetTempPath())
$tempFolder = $asyncTemp.AsTask().Result
$asyncCreate = $tempFolder.CreateFileAsync("temp_logo.png", [Windows.Storage.CreationCollisionOption]::ReplaceExisting)
$outFile = $asyncCreate.AsTask().Result

$asyncStream = $outFile.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)
$stream = $asyncStream.AsTask().Result

$options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
# High resolution render
$options.DestinationWidth = [uint32]($page.Size.Width * 3)
$options.DestinationHeight = [uint32]($page.Size.Height * 3)

$asyncRender = $page.RenderToStreamAsync($stream, $options)
$asyncRender.AsTask().Wait()

$asyncFlush = $stream.FlushAsync()
$asyncFlush.AsTask().Wait()
$stream.Dispose()

Copy-Item -Path $tempPng -Destination $OutPng -Force
Remove-Item -Path $tempPng -Force -ErrorAction SilentlyContinue

Write-Output "Logo saved to $OutPng successfully."
