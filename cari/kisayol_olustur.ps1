# Egeser-Cari kisayolunu masaustune ve Baslat menusune olusturur (logolu simge: Egeser-Cari.ico).
# kur.bat tarafindan cagrilir; elle de calistirilabilir:  powershell -ExecutionPolicy Bypass -File kisayol_olustur.ps1
$ErrorActionPreference = 'Stop'
$klasor = Split-Path -Parent $MyInvocation.MyCommand.Path
$ad = 'Egeser-Cari'
$hedefler = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
$eskiAdlar = @('Cari.lnk', 'Cari Program.lnk')          # onceki surumlerden kalan kisayollar
$kabuk = New-Object -ComObject WScript.Shell
foreach ($dizin in $hedefler) {
  if (-not (Test-Path $dizin)) { continue }
  foreach ($eski in $eskiAdlar) { $y = Join-Path $dizin $eski; if (Test-Path $y) { Remove-Item $y -Force } }
  $k = $kabuk.CreateShortcut((Join-Path $dizin ($ad + '.lnk')))
  $k.TargetPath = Join-Path $klasor 'baslat.bat'
  $k.WorkingDirectory = $klasor
  $k.WindowStyle = 7                                     # simge durumunda (siyah pencere gorunmez)
  $k.IconLocation = (Join-Path $klasor ($ad + '.ico')) + ',0'
  $k.Description = 'Egeser-Cari: cari, kasa, gider ve malzeme takibi'
  $k.Save()
  Write-Host ('Kisayol: ' + (Join-Path $dizin ($ad + '.lnk')))
}
