# Zdefiniuj ścieżkę do folderu, który chcesz skompresować
$Source = "C:\Users\ziutus\git\stalker_all\stalker-server\lambdas\call_to_rds"

# Zdefiniuj ścieżki do plików, które chcesz skompresować
$Files = "C:\Users\ziutus\git\stalker_all\stalker-server\lambdas\call_to_rds\", "C:\Path\To\Your\File2","C:\Path\To\Your\File3"

# Zdefiniuj ścieżkę do pliku ZIP, który chcesz utworzyć
$Destination = "C:\Path\To\Your\Destination.zip"

# Utwórz tymczasowy folder
$TempFolder = "C:\Path\To\Your\TempFolder"
New-Item -ItemType directory -Path $TempFolder -Force

# Skopiuj wybrane pliki do folderu tymczasowego
$Files | Copy-Item -Destination $TempFolder

# Załaduj moduł Compress-Zip (wymagany w PowerShell 5.0 i nowszych)
Add-Type -A 'System.IO.Compression.FileSystem'

# Utwórz archiwum ZIP z folderu tymczasowego
[System.IO.Compression.ZipFile]::CreateFromDirectory($TempFolder, $Destination)

# Usuń folder tymczasowy
Remove-Item -Recurse -Force $TempFolder