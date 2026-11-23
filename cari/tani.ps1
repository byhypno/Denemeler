# Egeser-Cari tani araci: programin neden acilmadigini/durdugunu gosteren rapor (tani.txt) uretir.
# tani.bat tarafindan cagrilir. Hicbir veriyi degistirmez/silmez.
$ErrorActionPreference = 'Continue'
$klasor = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $klasor
$rapor = Join-Path $klasor 'tani.txt'
$py = Join-Path $klasor '.venv\Scripts\python.exe'
function Yaz($baslik, $icerik) {
  Add-Content -Path $rapor -Encoding UTF8 -Value ("`r`n=== " + $baslik + " ===`r`n" + $icerik)
}
Set-Content -Path $rapor -Encoding UTF8 -Value ('Egeser-Cari tani raporu - ' + (Get-Date))
Yaz 'Klasor' $klasor
Yaz 'Windows' ((Get-CimInstance Win32_OperatingSystem).Caption + ' ' + [Environment]::OSVersion.Version)

if (-not (Test-Path $py)) {
  Yaz 'SORUN' '.venv bulunamadi: kur.bat calistirilmamis ya da klasor tasinmis/silinmis.'
} else {
  Yaz 'Python' ((& $py --version 2>&1) | Out-String)
  Yaz 'Paketler' ((& $py -m pip list 2>&1) | Out-String)
  Yaz 'manage.py check' ((& $py manage.py check 2>&1) | Out-String)
}

Yaz 'Veri klasoru' ((Get-ChildItem (Join-Path $klasor 'veri') -ErrorAction SilentlyContinue | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String))
$log = Join-Path $klasor 'veri\sunucu.log'
if (Test-Path $log) {
  Yaz 'sunucu.log (son 80 satir)' ((Get-Content $log -Tail 80 -Encoding UTF8) -join "`r`n")
} else {
  Yaz 'sunucu.log' 'yok (guncelleme uygulanmamis ya da sunucu hic baslamamis)'
}
Yaz 'Python islemleri (su an calisan)' ((Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime, Path | Format-Table -AutoSize | Out-String))

$dinleyen = netstat -ano | Select-String ':8000'
Yaz 'Port 8000' (($dinleyen | Out-String))
$cikti = Join-Path $klasor 'tani_sunucu_cikti.txt'
$hata = Join-Path $klasor 'tani_sunucu_hata.txt'
if (($dinleyen | Out-String) -match 'LISTENING') {
  Yaz 'Sunucu denemesi' 'Port 8000 ZATEN kullanimda (program calisiyor olabilir). Tarayicida http://127.0.0.1:8000 adresini acmayi deneyin.'
} elseif (Test-Path $py) {
  $p = Start-Process -FilePath $py -ArgumentList 'manage.py', 'sunucu', '--tarayici-yok' -WorkingDirectory $klasor -RedirectStandardOutput $cikti -RedirectStandardError $hata -PassThru -WindowStyle Hidden
  Start-Sleep -Seconds 10
  if ($p.HasExited) {
    $durum = 'SUNUCU 10 saniye icinde DURDU. Cikis kodu: ' + $p.ExitCode
  } else {
    try {
      $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/giris/' -UseBasicParsing -TimeoutSec 5
      $durum = 'Sunucu CALISIYOR; giris sayfasi HTTP ' + $r.StatusCode
    } catch {
      $durum = 'Sunucu islemi var ama yanit vermiyor: ' + $_.Exception.Message
    }
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  }
  Yaz 'Sunucu denemesi (10 sn)' ($durum + "`r`n--- cikti ---`r`n" + (Get-Content $cikti -Raw -ErrorAction SilentlyContinue) + "`r`n--- hata ---`r`n" + (Get-Content $hata -Raw -ErrorAction SilentlyContinue))
  Remove-Item $cikti, $hata -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host ('Rapor hazir: ' + $rapor)
Write-Host 'Not Defteri acilacak; icerigini (ya da tani.txt dosyasini) gonderin.'
Start-Process notepad.exe $rapor
