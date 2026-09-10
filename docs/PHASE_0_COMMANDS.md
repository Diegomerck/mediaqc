# Phase 0 command record

Exact PowerShell command invocations dispatched during this task, in order.
This includes inspection, failed attempts, approved retries, installs and checks.
Conditional clauses in an invocation only ran when their conditions allowed.
The npm script expansions are documented in DEVELOPMENT.md and package.json;
the individual gate outcomes are recorded in PHASE_0.md. File edits used the
apply_patch tool and formatter commands. No commit, push or branch switch ran.

## Invocation 1

```powershell
Get-Location; git status --short --branch; rg --files -g '*.md' -g '!node_modules' -g '!target' -g '!vendor'; Get-ChildItem -Force
```

## Invocation 2

```powershell
Get-Content -Raw MASTER_SPEC.md; Get-Content -Raw AGENTS.md; Get-Content -Raw README.md; Get-Content -Raw specs/01_PRODUCT_SPEC.md; Get-Content -Raw specs/02_ARCHITECTURE.md; Get-Content -Raw specs/03_DATABASE.md
```

## Invocation 3

```powershell
Get-Content -Raw specs/04_DETECTOR_SPEC.md; Get-Content -Raw specs/05_QC_PROFILE_SPEC.md; Get-Content -Raw specs/06_IPC_SPEC.md; Get-Content -Raw specs/07_UI_SPEC.md; Get-Content -Raw specs/08_AI_SPEC.md; Get-Content -Raw specs/09_TESTING_SPEC.md; Get-Content -Raw specs/10_WINDOWS_BUILD.md; Get-Content -Raw .gitattributes; Get-Content -Raw SPEC_MANIFEST.json
```

## Invocation 4

```powershell
$names = 'node','npm','rustc','cargo','rustup','python','py','uv','cl'; foreach ($name in $names) { Get-Command $name -ErrorAction SilentlyContinue | Select-Object Name,Source }; node --version; npm --version; rustc --version; cargo --version; rustup show; py --list-paths; python --version; uv --version; $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'; if (Test-Path $vswhere) { & $vswhere -products * -format json }; Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\*' -ErrorAction SilentlyContinue | Select-Object name,pv
```

## Invocation 5

```powershell
Get-Content -Raw specs/06_IPC_SPEC.md; Get-Content -Raw specs/07_UI_SPEC.md
```

## Invocation 6

```powershell
Get-ChildItem 'C:\Program Files\Microsoft Visual Studio','C:\Program Files (x86)\Microsoft Visual Studio','C:\Program Files (x86)\Windows Kits','C:\Users\Diegomerck\.cargo\bin','C:\Users\Diegomerck\AppData\Local\Programs\Python' -ErrorAction SilentlyContinue | Select-Object FullName; Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\*' -ErrorAction SilentlyContinue | Format-List name,pv; git ls-files
```

## Invocation 7

```powershell
& 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' --version; & 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip --version; npm view react version; npm view vite version; npm view vitest version; npm view typescript version; npm view @tauri-apps/cli version
```

## Invocation 8

```powershell
Get-ChildItem Env: | Where-Object Name -Match 'PROXY|NPM|CARGO|RUST|UV_' | Select-Object Name; Get-ChildItem 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback' -Filter '*uv*'; Get-ChildItem 'C:\Program Files' -Name
```

## Invocation 9

```powershell
npm view react version --fetch-retries=0 --fetch-timeout=15000
```

## Invocation 10

```powershell
npm view react version --fetch-retries=0 --fetch-timeout=15000; npm view vite version; npm view vitest version; npm view typescript version; npm view @tauri-apps/cli version; npm view @vitejs/plugin-react version; npm view eslint version; npm view typescript-eslint version; npm view eslint-plugin-react-hooks version; npm view eslint-plugin-react-refresh version; npm view prettier version; npm view @testing-library/react version; npm view @testing-library/jest-dom version; npm view jsdom version; npm view @types/react version; npm view @types/react-dom version; npm view @types/node version; npm view globals version
```

## Invocation 11

```powershell
New-Item -ItemType Directory -Force .tools | Out-Null; & 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install --target .tools/bootstrap uv --disable-pip-version-check --retries 0 --timeout 15
```

## Invocation 12

```powershell
& 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install --target .tools/bootstrap uv --disable-pip-version-check --retries 0 --timeout 15 --index-url https://pypi.org/simple
```

## Invocation 13

```powershell
npm view typescript-eslint@8.70.0 peerDependencies --json; npm view eslint-plugin-react-hooks@7.1.1 peerDependencies --json; npm view @vitejs/plugin-react@6.1.1 peerDependencies --json; npm view vitest@5.0.0 engines --json; Invoke-RestMethod https://crates.io/api/v1/crates/tauri | Select-Object -ExpandProperty crate | Select-Object newest_version; Invoke-RestMethod https://crates.io/api/v1/crates/tauri-build | Select-Object -ExpandProperty crate | Select-Object newest_version
```

## Invocation 14

```powershell
Invoke-WebRequest https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe -OutFile .tools/rustup-init.exe -TimeoutSec 20
```

## Invocation 15

```powershell
Invoke-WebRequest https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe -OutFile .tools/rustup-init.exe -TimeoutSec 60; if (-not $?) { exit 1 }; $env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:RUSTUP_INIT_SKIP_MSVC_CHECK = '1'; & .tools/rustup-init.exe -y --no-modify-path --profile minimal --default-toolchain 1.94.0 --default-host x86_64-pc-windows-msvc --component rustfmt,clippy; exit $LASTEXITCODE
```

## Invocation 16

```powershell
git status --short; Get-Content package.json; Get-ChildItem .tools/bootstrap/bin,.tools/bootstrap/Scripts -ErrorAction SilentlyContinue | Select-Object FullName; Get-Content pyproject.toml
```

## Invocation 17

```powershell
rg --files --hidden --no-ignore .tools/bootstrap -g '*uv*.exe'; npm install --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=15000
```

## Invocation 18

```powershell
npm install --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm ci --fetch-retries=0 --fetch-timeout=30000; exit $LASTEXITCODE
```

## Invocation 19

```powershell
Get-ChildItem .tools/bootstrap/bin; $env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'; & .tools/bootstrap/bin/uv.exe lock --python 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; & .tools/bootstrap/bin/uv.exe sync --locked --python 'C:\Users\Diegomerck\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; exit $LASTEXITCODE
```

## Invocation 20

```powershell
npm install --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm ci --fetch-retries=0 --fetch-timeout=30000; exit $LASTEXITCODE
```

## Invocation 21

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; & .tools/cargo/bin/cargo.exe generate-lockfile --manifest-path apps/desktop/src-tauri/Cargo.toml
```

## Invocation 22

```powershell
Get-Content -Raw uv.lock; git diff --exit-code -- MASTER_SPEC.md AGENTS.md README.md SPEC_MANIFEST.json specs
```

## Invocation 23

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; cargo generate-lockfile --manifest-path apps/desktop/src-tauri/Cargo.toml; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; cargo fetch --locked --manifest-path apps/desktop/src-tauri/Cargo.toml; exit $LASTEXITCODE
```

## Invocation 24

```powershell
npm run format; npm run lint; npm run typecheck; npm run test:frontend; npm run build
```

## Invocation 25

```powershell
npm view @eslint/js version; npm view jsdom@27.0.1 engines --json; npm view jsdom@28.0.0 engines --json
```

## Invocation 26

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'; $env:PATH = (Join-Path $PWD '.tools/bootstrap/bin') + ';' + (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; $env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; uv run --locked ruff format --check .; uv run --locked ruff check .; uv run --locked mypy; uv run --locked pytest; npm run rust:format:check; npm run format
```

## Invocation 27

```powershell
Get-Content node_modules/@testing-library/jest-dom/types/vitest.d.ts; Select-String -Path node_modules/vitest/dist/chunks/config.d.CU_b-wJj.d.ts -Pattern 'interface Assertion' -Context 2,2; Get-Content node_modules/@tauri-apps/cli/config.schema.json -TotalCount 30; Get-Content apps/desktop/src-tauri/Cargo.lock -TotalCount 20
```

## Invocation 28

```powershell
rg -n 'icon.ico|default_window_icon|icon.png' .tools/cargo/registry/src -g '*.rs' -g '!windows*' --max-count 5
```

## Invocation 29

```powershell
npm install --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm ci --fetch-retries=0 --fetch-timeout=30000; exit $LASTEXITCODE
```

## Invocation 30

```powershell
Select-String -Path .tools/cargo/registry/src/index.crates.io-1949cf8c6b5b557f/tauri-codegen-2.6.3/src/context.rs -Pattern 'default_window_icon|icon.ico|icon.png' -Context 3,16; Select-String -Path .tools/cargo/registry/src/index.crates.io-1949cf8c6b5b557f/tauri-build-2.5.6/src/lib.rs -Pattern 'icon.ico' -Context 8,18
```

## Invocation 31

```powershell
git status --short --branch; Get-ChildItem .cache/npm/_logs -File | Select-Object -Last 3 Name
```

## Invocation 32

```powershell
& node_modules/.bin/tauri.cmd icon config/app-icon.svg --output .cache/app-icons; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; New-Item -ItemType Directory -Force apps/desktop/src-tauri/icons | Out-Null; Copy-Item .cache/app-icons/icon.ico apps/desktop/src-tauri/icons/icon.ico; Copy-Item .cache/app-icons/icon.png apps/desktop/src-tauri/icons/icon.png
```

## Invocation 33

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'; $env:PATH = (Join-Path $PWD '.tools/bootstrap/bin') + ';' + (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; $env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; npm run format; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm run check 2>&1 | Tee-Object -FilePath .cache/phase0-check.log; exit $LASTEXITCODE
```

## Invocation 34

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; rustup show; npm run info --workspace @mediaqc/desktop; git diff --check; git diff --exit-code -- MASTER_SPEC.md AGENTS.md README.md SPEC_MANIFEST.json specs
```

## Invocation 35

```powershell
Get-Content .cache/phase0-check.log -Tail 90; git ls-files --others --exclude-standard; Get-ChildItem Env:CODEX_THREAD_ID -ErrorAction SilentlyContinue
```

## Invocation 36

```powershell
npm view vitest@4.0.18 dependencies --json; npm view @vitejs/plugin-react@5.1.2 peerDependencies --json; npm view vite@7.3.1 engines --json
```

## Invocation 37

```powershell
Get-ChildItem 'C:\Users\Diegomerck\.codex\sessions\2026\09\09' -Filter '*01a087a1-4ad7-7813-89ff-edde3fc109dc*' | Select-Object FullName
```

## Invocation 38

```powershell
npm install --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm ci --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm run typecheck; exit $LASTEXITCODE
```

## Invocation 39

```powershell
npm view vite@7 version --json; npm view vitest@4 version --json; npm view @vitejs/plugin-react@5 version --json; npm audit --json
```

## Invocation 40

```powershell
Get-Content 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl' -TotalCount 2 | ForEach-Object { $entry = $_ | ConvertFrom-Json; $entry | Select-Object type; $entry.payload | Select-Object type,role,name }; Get-Content .cache/phase0-check.log -Tail 22
```

## Invocation 41

```powershell
npm run typecheck
```

## Invocation 42

```powershell
npm install --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm ci --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm run typecheck; exit $LASTEXITCODE
```

## Invocation 43

```powershell
$entries = Get-Content 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl' | ForEach-Object { $_ | ConvertFrom-Json }; $entries | Where-Object { $_.payload.type -eq 'function_call' } | Select-Object -First 2 -ExpandProperty payload | Select-Object name,arguments
```

## Invocation 44

```powershell
$entries = Get-Content 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl' | ForEach-Object { $_ | ConvertFrom-Json }; $entries | Where-Object { $_.payload.name -eq 'exec' } | Select-Object -First 1 -ExpandProperty payload | ConvertTo-Json -Depth 3
```

## Invocation 45

```powershell
npm ls esbuild vite vitest; node .cache/export-commands.mjs 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl'
```

## Invocation 46

```powershell
node --input-type=module -e "import fs from 'node:fs'; for (const path of ['apps/frontend/node_modules/vitest/package.json','node_modules/vitest/package.json','apps/frontend/node_modules/vite/package.json','node_modules/vite/package.json']) { if (fs.existsSync(path)) { const p=JSON.parse(fs.readFileSync(path,'utf8')); console.log(JSON.stringify({path,version:p.version,dependencies:p.dependencies})); } }"
```

## Invocation 47

```powershell
npm update esbuild --package-lock-only --ignore-scripts --fetch-retries=0 --fetch-timeout=30000; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm ci --fetch-retries=0 --fetch-timeout=30000; exit $LASTEXITCODE
```

## Invocation 48

```powershell
node .cache/export-commands.mjs 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl'; npm ls esbuild vite vitest
```

## Invocation 49

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'; $env:PATH = (Join-Path $PWD '.tools/bootstrap/bin') + ';' + (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; $env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; npm run format; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; npm run check 2>&1 | Tee-Object -FilePath .cache/phase0-final-check.log; exit $LASTEXITCODE
```

## Invocation 50

```powershell
Get-Content .cache/phase0-final-check.log -Tail 70; git diff --exit-code -- MASTER_SPEC.md AGENTS.md README.md SPEC_MANIFEST.json specs; git diff --check; git status --porcelain=v1 -uall
```

## Invocation 51

```powershell
node .cache/export-commands.mjs 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl'; & node_modules/.bin/prettier.cmd --config config/prettier.json --write docs/PHASE_0.md docs/PHASE_0_COMMANDS.md; & node_modules/.bin/prettier.cmd --config config/prettier.json --check docs/PHASE_0.md docs/PHASE_0_COMMANDS.md; git diff --check; git diff --exit-code -- MASTER_SPEC.md AGENTS.md README.md SPEC_MANIFEST.json specs; git status --short --branch; (git ls-files --others --exclude-standard | Measure-Object).Count
```

## Invocation 52

```powershell
git status --short --branch; Get-Content -Raw package.json; Get-Content -Raw docs/PHASE_0.md; Get-Content -Raw tools/check.mjs; Get-Content -Raw rust-toolchain.toml; Get-Content -Raw apps/desktop/src-tauri/Cargo.toml; Get-ChildItem .tools -Name; & 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe' -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json
```

## Invocation 53

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; $nativeFailed = $false; foreach ($gate in @('rust:check','rust:lint','rust:test','desktop:build')) { npm run $gate 2>&1 | Tee-Object -FilePath (Join-Path $PWD ".cache/revalidation-$gate.log".Replace(':','-')); if ($LASTEXITCODE -ne 0) { $nativeFailed = $true } }; if ($nativeFailed) { exit 1 }
```

## Invocation 54

```powershell
Get-Content .cache/revalidation-rust-check.log -Tail 25; Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\Lib' -Directory | Select-Object -ExpandProperty Name; Get-ChildItem 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC' -Directory | Select-Object -ExpandProperty Name; Get-Content -Raw .cache/export-commands.mjs
```

## Invocation 55

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'powershell|pwsh' -and $_.CommandLine -like '*nativeFailed*' -and $_.CommandLine -like '*Tee-Object*' } | Select-Object ProcessId,ParentProcessId,CommandLine
```

## Invocation 56

```powershell
Get-Content -Raw apps/desktop/src-tauri/Cargo.toml; git status --short --branch
```

## Invocation 57

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; cargo update -p tauri --precise 2.11.5 --manifest-path apps/desktop/src-tauri/Cargo.toml --offline
```

## Invocation 58

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; cargo update -p tauri --precise 2.11.5 --manifest-path apps/desktop/src-tauri/Cargo.toml; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; cargo fetch --locked --manifest-path apps/desktop/src-tauri/Cargo.toml; exit $LASTEXITCODE
```

## Invocation 59

```powershell
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; $nativeFailed = $false; foreach ($gate in @('rust:check','rust:lint','rust:test','desktop:build')) { npm run $gate 2>&1 | Tee-Object -FilePath (Join-Path $PWD ".cache/aligned-$gate.log".Replace(':','-')); if ($LASTEXITCODE -ne 0) { $nativeFailed = $true } }; if ($nativeFailed) { exit 1 }
```

## Invocation 60

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'; $env:CARGO_HOME = Join-Path $PWD '.tools/cargo'; $env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'; $env:PATH = (Join-Path $PWD '.tools/bootstrap/bin') + ';' + (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH; npm run check 2>&1 | Tee-Object -FilePath .cache/phase0-native-ready-check.log; exit $LASTEXITCODE
```

## Invocation 61

```powershell
node .cache/refresh-phase0-native-report.mjs; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; node .cache/export-commands.mjs 'C:\Users\Diegomerck\.codex\sessions\2026\09\09\rollout-2026-09-09T13-24-49-01a087a1-4ad7-7813-89ff-edde3fc109dc.jsonl'; & node_modules/.bin/prettier.cmd --config config/prettier.json --write docs/PHASE_0.md docs/PHASE_0_COMMANDS.md; & node_modules/.bin/prettier.cmd --config config/prettier.json --check docs/PHASE_0.md docs/PHASE_0_COMMANDS.md; git diff --check; git diff --exit-code -- MASTER_SPEC.md AGENTS.md README.md SPEC_MANIFEST.json specs; Select-String -Path docs/PHASE_0.md -Pattern 'Tauri crate|tauri-build|exit criteria|exit code'; Get-Item apps/desktop/src-tauri/target/release/mediaqc-desktop.exe | Select-Object FullName,Length; git status --short --branch; (git ls-files --others --exclude-standard | Measure-Object).Count
```
