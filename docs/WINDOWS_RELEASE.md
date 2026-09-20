# MediaQC Windows release

This internal V1 candidate is unsigned unless Authenticode verification says otherwise.
It includes no production AI provider or model. Use AI OFF for deterministic QC.

## Installer and portable prerequisites

The NSIS x64 installer installs per user and embeds Microsoft's Evergreen WebView2
offline installer. Installation does not need an internet download. Windows and
corporate policy may still require administrator/IT involvement for runtime setup.
Do not bypass security prompts, allowlisting or endpoint policy.

The portable ZIP includes MediaQC.exe, Python and numerical/reporting dependencies,
FFmpeg/ffprobe, profiles and report resources. Extract the whole folder before use.
It requires an already installed Microsoft Evergreen WebView2 Runtime. It is not
self-contained with respect to that OS/runtime prerequisite. If WebView2 is absent,
use the MediaQC installer or ask IT to provision Microsoft's offline runtime package.
The portable app never installs or downloads the runtime. A fixed runtime is not used.
Python, Node/npm, Rust, Git, Visual Studio, FFmpeg and CUDA are not end-user prerequisites.

Choose a writable project directory outside the extracted/installed application
folder and outside source-media directories. Projects contain SQLite, cache,
evidence and reports; sources stay in their original locations and are read-only.
Engine logs/recovery state and WebView2 user data use Tauri's per-user application
directories. Selecting the project location also selects its cache volume; a separate
global cache-location setting is not currently implemented.

Do not remove projects to uninstall. The NSIS uninstaller removes installed
application files; user-selected project/source directories must be retained.
For portable use, close the application before removing its extracted folder.
WebView2 is a shared runtime and must not be removed by MediaQC's uninstaller.

## Build and signing

Use the pinned developer toolchains described in DEVELOPMENT.md. Prepare FFmpeg
with `npm run media:prepare` before building. Developer dependency downloads are
build-time operations only. Run the complete gate once with `npm run check`; it
builds the engine/frontend once and compiles the prepared desktop release.
Then run `npm run release:installer` and `npm run release:portable` once.
Tauri downloads the NSIS tooling and Microsoft offline runtime at packaging time
if not cached. Archive the installer, portable ZIP, SHA-256 file and release manifest.
Record the offline runtime's actual version/hash from the packaging cache; Evergreen
packaging is not a byte-for-byte reproducible or pinned fixed-runtime distribution.

For production signing, copy config/windows-signing.example.json to a local ignored
location, replace both placeholders with the actual certificate thumbprint and
provider RFC3161 timestamp URL, then pass that config after tauri.release.conf.json
to `tauri bundle`. Never check credentials/private keys into source control.
Sign application-owned executables (including engine) before assembling artifacts;
verify signatures using `Get-AuthenticodeSignature`. Tauri's installer signing alone
is not evidence that every nested executable is signed. Unsigned internal builds
are acceptable for validation, not proof of production signing/reputation readiness.

FFmpeg 8.1.2 is the existing checksum-pinned Gyan GPL-3.0-or-later build. Its LICENSE,
README and complete version/configuration provenance accompany the engine. Python
dependency metadata/licenses are collected into the runtime. Lockfiles accompany
the portable build. Before public redistribution, the owner must resolve source
availability and all applicable FFmpeg/codec and dependency license obligations.

## Clean Windows 10/11 validation procedure

Perform separately on clean supported Windows 10 x64 and Windows 11 x64 snapshots,
without Python, Node, Git, Visual Studio, FFmpeg or CUDA. Record Windows build,
CPU/RAM, GPU availability, Defender status, user privilege and artifact SHA-256.
Keep Defender and corporate security controls enabled. Record each check as
PASS, FAIL or UNVERIFIED with screenshots/logs and actual observed results.

1. Copy installer, portable ZIP and locally generated WAV/MP3/MP4/MXF fixtures to
   the machine. Hash fixtures with `Get-FileHash -Algorithm SHA256` and record size
   and LastWriteTimeUtc. Include an unsupported/corrupt sample and long media.
2. Record installed WebView2 version. Test the installer on a snapshot without
   WebView2 as well as one with it. Disconnect networking before installation.
3. Run the installer as a standard user. Record any elevation/runtime prompt and
   installed path. Verify Start Menu launch and runtime installation with no download.
4. Launch with networking disconnected. Create a project in a separate writable
   directory. Inspect/analyze all four formats with AI OFF and a selected profile.
   Review waveform/spectrogram/video evidence; set confirmed, false-positive and
   ignored dispositions; verify overall-result updates. Export/open HTML and PDF.
5. Inspect corrupt/unsupported media; verify a structured error and usable app.
   Cancel a long analysis, verify CANCELLED and no owned FFmpeg/ffprobe/worker
   remains using Task Manager/Process Explorer. Close the app during another run;
   verify its process tree exits. Relaunch and reopen the project/history/reports.
6. With authorized administrator/IT assistance, block outbound traffic for the
   installed desktop, engine, ffmpeg, ffprobe and relevant WebView2 subprocesses
   using Windows Defender Firewall. Record rule names, paths, active profiles and
   enforcement evidence. Repeat steps 4–5 with networking otherwise connected.
   Restore only the rules added for this test afterward. Disconnection, empty PATH
   and static code review alone do not establish firewall-enforced acceptance.
7. Rehash source files and compare timestamps. Verify no sidecars appeared next
   to sources and no full source copy appeared in the project.
8. Close MediaQC and uninstall using Windows Installed Apps. Verify executable
   and Start Menu entry removed, project/evidence/reports/source hashes retained,
   shared WebView2 retained. Reinstall and reopen the retained project.
9. On a fresh snapshot with WebView2 installed, extract portable ZIP into a path
   containing spaces/non-ASCII characters. Launch MediaQC.exe from another current
   directory as a standard user. Repeat steps 4–7. Verify resources were not written.
10. On a snapshot without WebView2, record portable prerequisite failure. Provision
    WebView2 via the approved offline installer and retest. Never treat failure before
    provisioning as successful self-contained operation.
11. On CPU-only hardware, run 1080p and 4K plus short/long duration comparisons.
    Record format/codec/resolution/duration, profile snapshot, inspection latency,
    analysis wall time, media-duration/wall-time ratio and sampled process-tree peak
    memory. Confirm responsive UI while QC runs. Cache may grow on disk with frame
    count; decoded media must not accumulate in memory. Retain measurement JSON.

Clean-machine, firewall, GUI responsiveness and physical uninstall results must
remain UNVERIFIED until actually observed. Development-PC smokes are complementary.

## Automated measurements on a development PC

Extract the produced ZIP to a fresh path. With the pinned developer Python, run:

```powershell
.venv/Scripts/python.exe tools/validate_release.py C:\path\to\extracted\MediaQC C:\fixtures\sample.mp4 --output C:\validation\sample
.venv/Scripts/python.exe tools/benchmark_release.py C:\path\to\extracted\MediaQC --output C:\validation\benchmarks
```

Output directories must be new and writable. The benchmark generates 30/120-second
1080p H.264/AAC, 15-second 4K H.264/AAC, and a sparse 4-GiB RF64 PCM file on NTFS.
The RF64 test measures inspection and active cancellation, not complete six-hour QC.
It aborts if sparse allocation cannot be enabled. Analysis uses the unchanged
general_technical_qc 1.2.0 profile (320x180 frame measurements, all frames, software
decode and CPU DSP, AI OFF). Process-tree memory is sampled every 100 ms; this is a
sampled peak, not an exact high-water mark. JSON preserves machine and per-run data.
These developer runners are not prerequisites for using the application.

## Commands for a clean-machine evidence record

Use PowerShell on the test VM. Substitute the actual paths and retain the outputs.
The fixture directory must contain only the test media, not changing log files.

```powershell
$fixtureDir = 'C:\MediaQC-Test\fixtures'
$recordDir = 'C:\MediaQC-Test\records'
New-Item -ItemType Directory -Path $recordDir -Force
Get-ComputerInfo | Out-File "$recordDir\machine.txt"
Get-ChildItem -LiteralPath $fixtureDir -File -Recurse |
  ForEach-Object {
    [pscustomobject]@{Path=$_.FullName; Length=$_.Length; Modified=$_.LastWriteTimeUtc;
      SHA256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
  } | Export-Csv "$recordDir\sources-before.csv" -NoTypeInformation
Get-FileHash 'C:\MediaQC-Test\MediaQC-setup.exe' -Algorithm SHA256
Get-AuthenticodeSignature 'C:\MediaQC-Test\MediaQC-setup.exe' | Format-List
```

After QC, reports and uninstall, repeat the source inventory into
`sources-after.csv`. This command must emit no differences:

```powershell
Compare-Object (Import-Csv "$recordDir\sources-before.csv") `
  (Import-Csv "$recordDir\sources-after.csv") -Property Path,Length,Modified,SHA256
```

For the firewall test only, an authorized administrator can run the following on
the disposable VM. Set the installed paths from the actual running processes;
WebView2's path varies by version. Include any additional owned executable observed
in the process tree. Do not run this on a shared workstation without IT authorization.

```powershell
$appDir = 'C:\Users\TESTUSER\AppData\Local\MediaQC'
$webviewExe = 'C:\Program Files (x86)\Microsoft\EdgeWebView\Application\VERSION\msedgewebview2.exe'
$testExecutables = @(
  "$appDir\mediaqc-desktop.exe",
  "$appDir\resources\engine\mediaqc-engine.exe",
  "$appDir\resources\engine\ffmpeg\ffmpeg.exe",
  "$appDir\resources\engine\ffmpeg\ffprobe.exe",
  $webviewExe
)
foreach ($exe in $testExecutables) {
  if (-not (Test-Path -LiteralPath $exe)) { throw "Correct the executable path: $exe" }
}
$ruleNames = @()
try {
  foreach ($exe in $testExecutables) {
    $ruleName = 'MediaQC-Phase9-' + [guid]::NewGuid().ToString()
    New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Direction Outbound `
      -Action Block -Program $exe -Profile Any -Enabled True -ErrorAction Stop
    $ruleNames += $ruleName
  }
  Get-NetFirewallProfile | Format-List | Out-File "$recordDir\firewall-profiles.txt"
  $ruleNames | ForEach-Object { Get-NetFirewallRule -Name $_ | Format-List } |
    Out-File "$recordDir\firewall-rules.txt"
  Read-Host 'Verify active firewall enforcement, repeat QC/reports, save evidence; Enter to remove test rules'
} finally {
  $ruleNames | ForEach-Object { Remove-NetFirewallRule -Name $_ }
}
```

Record enforcement evidence from Windows Firewall logging or the organization's
approved diagnostic tooling. Merely creating rules while the firewall is disabled
does not pass the acceptance criterion. Runtime absence/presence and uninstall
checks require separate snapshot runs; do not remove a shared runtime on this PC.
