# WealthPilot 一键安装（Windows，PowerShell）。
#
#   irm https://raw.githubusercontent.com/Jackychen-12/wealthpilot/main/scripts/install.ps1 | iex
#
# 和 macOS / Linux 的 install.sh 做的是同样四件事，做完告诉你下一步：
#   1. 没有 uv 就先装 uv（Python 的包管理器，用它装依赖，不动你系统里的 Python）
#   2. 把代码放到 %USERPROFILE%\.wealthpilot\app（已经有就更新）
#   3. 装依赖；机器上有 Node.js 就顺手把网页版构建出来，没有也不影响终端使用
#   4. 在 %USERPROFILE%\.local\bin 放一个 wealthpilot 命令，并把这个目录加进你自己的 PATH
# 你的数据（配置、数据库、研究方法）都在 %USERPROFILE%\.wealthpilot，和代码分开，升级、重装都不会动它。
#
# 可以用环境变量改默认行为（先 $env:名字 = '值'，再运行上面那一行）：
#   WEALTHPILOT_KEY          装完直接把模型 Key 配好
#   WEALTHPILOT_HOME         数据放哪
#   WEALTHPILOT_DIR          代码放哪（默认 数据目录\app）
#   WEALTHPILOT_BIN_DIR      命令放哪
#   WEALTHPILOT_REPO / WEALTHPILOT_BRANCH   从哪个仓库、哪个分支装
#   WEALTHPILOT_SKIP_WEB=1   不构建网页版
#   WEALTHPILOT_NO_PATH=1    不改 PATH（自己加）
#   WEALTHPILOT_UNINSTALL=1  卸载：只删代码和命令，数据留着
#
# 这个文件是不带 BOM 的 UTF-8。请用上面那一行运行；把它存成文件再用旧版 Windows PowerShell 5.1 打开，中文会被读乱。

function Install-WealthPilot {
  $ErrorActionPreference = 'Stop'
  if ('中'.Length -ne 1) {
    Write-Host 'This script was read with the wrong text encoding. Run it like this instead:'
    Write-Host '  irm https://raw.githubusercontent.com/Jackychen-12/wealthpilot/main/scripts/install.ps1 | iex'
    return
  }

  $Repo   = if ($env:WEALTHPILOT_REPO)    { $env:WEALTHPILOT_REPO }    else { 'https://github.com/Jackychen-12/wealthpilot.git' }
  $Branch = if ($env:WEALTHPILOT_BRANCH)  { $env:WEALTHPILOT_BRANCH }  else { 'main' }
  $Data   = if ($env:WEALTHPILOT_HOME)    { $env:WEALTHPILOT_HOME }    else { Join-Path $HOME '.wealthpilot' }
  $App    = if ($env:WEALTHPILOT_DIR)     { $env:WEALTHPILOT_DIR }     else { Join-Path $Data 'app' }
  $Bin    = if ($env:WEALTHPILOT_BIN_DIR) { $env:WEALTHPILOT_BIN_DIR } else { Join-Path $HOME '.local\bin' }
  $Shim   = Join-Path $Bin 'wealthpilot.cmd'
  $Exe    = Join-Path $App 'backend\.venv\Scripts\wealthpilot.exe'

  function Step($text) { Write-Host ''; Write-Host $text -ForegroundColor White }
  function Has($name)  { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
  # 不用 exit：这段脚本是直接在你的窗口里运行的，exit 会把窗口关掉
  function Fail($text) { throw $text }

  if ($env:WEALTHPILOT_UNINSTALL -eq '1') {
    if (Test-Path $Shim) { Remove-Item -Force $Shim }
    if (Test-Path $App)  { Remove-Item -Recurse -Force $App }
    Write-Host '已卸载：命令和代码都删了。'
    Write-Host "你的数据还在 $Data （配置、数据库、研究方法）。确定不要了再自己删。"
    return
  }

  if (-not (Has 'git')) { Fail '需要先装 git：winget install --id Git.Git -e ，装完新开一个 PowerShell 窗口再运行一次。' }

  Step '1/4 准备 uv'
  if (-not (Has 'uv')) {
    Write-Host '没有找到 uv，用它官方的安装脚本装一个（装在你的用户目录下，不需要管理员权限）…'
    # 放在子进程里跑：它自己的脚本里有 exit，不能让它把这个窗口带走
    powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
    $env:Path = (Join-Path $HOME '.local\bin') + ';' + $env:Path
    if (-not (Has 'uv')) { Fail 'uv 装完了但找不到命令。新开一个 PowerShell 窗口再运行一次这个脚本。' }
  }
  Write-Host ('✓ ' + (uv --version))

  Step "2/4 获取代码 → $App"
  New-Item -ItemType Directory -Force -Path $Data | Out-Null
  if (Test-Path (Join-Path $App '.git')) {
    git -C $App fetch --quiet origin $Branch
    if ($LASTEXITCODE -ne 0) { Fail '没能连上 GitHub，稍后重新运行这个脚本即可。' }
    git -C $App checkout --quiet $Branch
    git -C $App pull --quiet --ff-only origin $Branch
    if ($LASTEXITCODE -ne 0) { Fail "代码目录里有本地改动，没法直接更新：$App" }
    Write-Host '✓ 已更新到最新'
  } else {
    if (Test-Path $App) { Fail "$App 已经存在但不是 WealthPilot 的代码目录。换个位置：先设 WEALTHPILOT_DIR 再运行。" }
    git clone --quiet --depth 1 --branch $Branch $Repo $App
    if ($LASTEXITCODE -ne 0) { Fail '代码没下载下来。多半是连不上 GitHub，稍后重新运行这个脚本即可。' }
    Write-Host '✓ 已下载'
  }

  Step '3/4 安装依赖'
  Push-Location (Join-Path $App 'backend')
  try { uv sync --quiet --extra feishu --extra dingtalk; $synced = $LASTEXITCODE } finally { Pop-Location }
  if ($synced -ne 0) { Fail '依赖没装上。多半是网络问题，稍后重新运行这个脚本即可（会接着装）。' }
  Write-Host '✓ 依赖装好了'
  if ($env:WEALTHPILOT_SKIP_WEB -eq '1') {
    Write-Host '· 按你的要求跳过了网页版'
  } elseif (Has 'npm.cmd') {
    Write-Host '构建网页版（一两分钟）…'
    # 明确叫 npm.cmd：同名的 npm.ps1 会被系统的脚本执行策略拦住
    Push-Location (Join-Path $App 'workbench')
    try {
      & npm.cmd ci --no-audit --no-fund --silent | Out-Null
      $built = $LASTEXITCODE
      if ($built -eq 0) { & npm.cmd run build --silent -- --outDir dist-app --emptyOutDir | Out-Null; $built = $LASTEXITCODE }
    } finally { Pop-Location }
    if ($built -eq 0) { Write-Host '✓ 网页版构建好了' } else { Write-Host '! 网页版没构建成，终端照样能用。之后想补：重新运行这个脚本。' }
  } else {
    Write-Host '! 没有找到 Node.js，先不构建网页版 —— 终端里什么都能做。想要网页版：装好 Node.js 后重新运行这个脚本。'
  }

  Step "4/4 放好 wealthpilot 命令 → $Bin"
  New-Item -ItemType Directory -Force -Path $Bin, (Join-Path $Data 'skills') | Out-Null
  # 自带的示例方法放进数据目录（已有的不覆盖）
  Get-ChildItem (Join-Path $App 'backend\skills') -Filter '*.md' -ErrorAction SilentlyContinue | ForEach-Object {
    $target = Join-Path $Data ('skills\' + $_.Name)
    if (-not (Test-Path $target)) { Copy-Item $_.FullName $target }
  }
  # 入口是一个 .cmd：设好数据目录，让 Python 一律按 UTF-8 读写，再把参数原样交给真正的程序。
  # .cmd 文件按系统的 OEM 代码页读，所以照那个编码写 —— 用户名是中文时路径才不会乱。
  # 在用户目录下面的路径写成 %USERPROFILE%\…，由 cmd 自己展开，中文用户名在任何语言的系统上都不会出错。
  function Portable($path) {
    if ($path.StartsWith($HOME, [StringComparison]::OrdinalIgnoreCase)) { '%USERPROFILE%' + $path.Substring($HOME.Length) } else { $path }
  }
  $cmdData = Portable $Data
  $cmdExe  = Portable $Exe
  $lines = @(
    '@echo off',
    "if not defined WEALTHPILOT_HOME set `"WEALTHPILOT_HOME=$cmdData`"",
    'set PYTHONUTF8=1',
    "if not exist `"$cmdExe`" (",
    '  echo WealthPilot is not installed here any more. Run the install script again; your data is kept.',
    '  exit /b 127',
    ')',
    "`"$cmdExe`" %*"
  )
  $oem = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
  [IO.File]::WriteAllText($Shim, ($lines -join "`r`n") + "`r`n", $oem)
  Write-Host '✓ 命令放好了'

  if ($env:WEALTHPILOT_KEY) {
    Step '配置模型'
    & $Shim setup --key $env:WEALTHPILOT_KEY --no-test
    if ($LASTEXITCODE -ne 0) { Write-Host '! 模型没配上，稍后运行：wealthpilot setup' }
  }

  Write-Host ''
  Write-Host '装好了。' -ForegroundColor White
  # 直接读写注册表里当前用户的 PATH，不展开里面的 %变量%，原来是什么样还是什么样，只在末尾加一项。
  $envKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
  $userPath = [string]$envKey.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
  if (($userPath -split ';') -notcontains $Bin) {
    if ($env:WEALTHPILOT_NO_PATH -eq '1') {
      Write-Host "注意：$Bin 不在 PATH 里，按你的要求没有改。自己加上之后新开一个窗口。"
    } else {
      $envKey.SetValue('Path', (($userPath.TrimEnd(';') + ';' + $Bin).TrimStart(';')), [Microsoft.Win32.RegistryValueKind]::ExpandString)
      # 设一个临时变量再删掉：这会通知已经开着的程序“环境变量变了”
      [Environment]::SetEnvironmentVariable('WEALTHPILOT_PATH_REFRESH', '1', 'User')
      [Environment]::SetEnvironmentVariable('WEALTHPILOT_PATH_REFRESH', $null, 'User')
      Write-Host "已把 $Bin 加进你自己的 PATH（只改了当前用户的，没动系统的）。新开的窗口里直接能用 wealthpilot。"
    }
  }
  $envKey.Close()
  if (($env:Path -split ';') -notcontains $Bin) { $env:Path = $Bin + ';' + $env:Path }   # 这个窗口里马上就能用

  & $Shim status | Out-Null          # status 在模型配好时返回 0
  if ($LASTEXITCODE -eq 0) {
    Write-Host '下一步：  wealthpilot          模型已经配好，直接开始用'
  } else {
    Write-Host '下一步：  wealthpilot setup    选一家模型、贴一个 Key（一分钟）'
    Write-Host '          wealthpilot          开始用'
  }
  Write-Host '以后升级：wealthpilot update    哪里不通：wealthpilot doctor'
}

try { Install-WealthPilot } catch { Write-Host ('✗ ' + $_.Exception.Message) -ForegroundColor Red }
