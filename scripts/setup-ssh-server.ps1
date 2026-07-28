param(
    [int]$Port = 22,
    [string]$AllowUser = $env:USERNAME,
    [switch]$DisablePassword   # 配好密钥后执行, 禁用密码认证
)

# ============================================================
# OpenSSH Server 公网加固配置脚本 (Windows 工作站)
# 用法:
#   首次配置(密码认证):  .\setup-ssh-server.ps1
#   自定义端口:          .\setup-ssh-server.ps1 -Port 22222
#   配好密钥后禁密码:    .\setup-ssh-server.ps1 -DisablePassword
# 必须以管理员身份运行
# ============================================================

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[X] 请用管理员身份运行本脚本!" -ForegroundColor Red
    Write-Host "    右键 PowerShell -> 以管理员身份运行" -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
$cfgPath = "C:\ProgramData\ssh\sshd_config"

Write-Host "`n========== OpenSSH Server 公网加固配置 ==========" -ForegroundColor Cyan
Write-Host "端口: $Port | 允许登录账户: $AllowUser | 禁用密码: $DisablePassword"

# ---------- 1. 安装 OpenSSH Server ----------
Write-Host "`n=== 1. 检查/安装 OpenSSH Server ===" -ForegroundColor Cyan
$cap = Get-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0" -ErrorAction SilentlyContinue
if (-not $cap) {
    $cap = Get-WindowsCapability -Online | Where-Object Name -like "OpenSSH.Server*"
}
Write-Host "当前状态: $($cap.State)"
if ($cap.State -ne "Installed") {
    Write-Host "安装中, 可能需要 1-2 分钟..." -ForegroundColor Yellow
    Add-WindowsCapability -Online -Name $cap.Name
    Write-Host "[OK] OpenSSH Server 已安装" -ForegroundColor Green
} else {
    Write-Host "[OK] 已安装, 跳过" -ForegroundColor Green
}

# ---------- 2. 启动 sshd 并设自动 ----------
Write-Host "`n=== 2. 启动 sshd 服务 ===" -ForegroundColor Cyan
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service sshd).Status -ne "Running") { Start-Service sshd }
$svc = Get-Service sshd
Write-Host "sshd: $($svc.Status) / $($svc.StartType)"

# ---------- 3. sshd_config 加固 ----------
Write-Host "`n=== 3. 加固 sshd_config ===" -ForegroundColor Cyan
if (-not (Test-Path $cfgPath)) {
    Write-Host "[!] sshd_config 不存在, 跳过加固 (重装 OpenSSH)" -ForegroundColor Red
} else {
    # 备份原配置
    Copy-Item $cfgPath "$cfgPath.bak" -Force

    # 读取现有配置, 分离 Match 块 (Match 块必须放文件末尾, 否则其后的全局指令会被误判为块内)
    $allLines = Get-Content $cfgPath
    $globalLines = @()
    $matchLines = @()
    $inMatch = $false
    foreach ($l in $allLines) {
        if ($l -match "^\s*Match\s") { $inMatch = $true }
        if ($inMatch) { $matchLines += $l } else { $globalLines += $l }
    }

    # 从全局行去掉要覆盖的指令
    $globalLines = $globalLines | Where-Object {
        $_ -notmatch "^\s*Port\s+" -and
        $_ -notmatch "^\s*MaxAuthTries\s+" -and
        $_ -notmatch "^\s*LoginGraceTime\s+" -and
        $_ -notmatch "^\s*AllowUsers\s+" -and
        $_ -notmatch "^\s*PasswordAuthentication\s+" -and
        $_ -notmatch "^\s*PubkeyAuthentication\s+" -and
        $_ -notmatch "^\s*PermitRootLogin\s+" -and
        $_ -notmatch "^\s*Subsystem\s+sftp"
    }

    $hardening = @(
        "# ===== 公网加固配置 (setup-ssh-server.ps1 生成) =====",
        "Port $Port",
        "MaxAuthTries 3",
        "LoginGraceTime 30",
        "AllowUsers $AllowUser",
        "PubkeyAuthentication yes",
        "PasswordAuthentication $(if ($DisablePassword) { 'no' } else { 'yes' })",
        "Subsystem sftp sftp-server.exe"
    )
    # 组装: 全局指令 + 加固配置 + Match 块 (Match 必须最后)
    $globalLines + $hardening + $matchLines | Set-Content $cfgPath -Encoding ASCII
    Write-Host "[OK] 已写入加固配置 (原配置备份: $cfgPath.bak)" -ForegroundColor Green
    Write-Host "  - Port $Port"
    Write-Host "  - MaxAuthTries 3 (爆破限制)"
    Write-Host "  - LoginGraceTime 30s (超时断开)"
    Write-Host "  - AllowUsers $AllowUser (白名单)"
    Write-Host "  - PasswordAuthentication $(if ($DisablePassword) { 'no (仅密钥)' } else { 'yes (临时, 配密钥后改 no)' })"
}

# ---------- 4. 默认 Shell (优先 PowerShell 7, 回退 5.1) ----------
Write-Host "`n=== 4. 默认 Shell ===" -ForegroundColor Cyan
$sshReg = "HKLM:\SOFTWARE\OpenSSH"
if (-not (Test-Path $sshReg)) { New-Item -Path $sshReg -Force | Out-Null }
$pwsh7 = "C:\Program Files\PowerShell\7\pwsh.exe"
$ps51  = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$shell = if (Test-Path $pwsh7) { $pwsh7 } else { $ps51 }
Set-ItemProperty -Path $sshReg -Name "DefaultShell" -Value $shell -Force
Set-ItemProperty -Path $sshReg -Name "DefaultShellCommandOption" -Value "/c" -Force
Write-Host "[OK] DefaultShell = $shell"

# ---------- 5. 防火墙规则 ----------
Write-Host "`n=== 5. 防火墙规则 (TCP $Port 入站) ===" -ForegroundColor Cyan
$ruleName = "OpenSSH-Server-In-TCP-$Port"
$rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -Name $ruleName -DisplayName "OpenSSH Server (port $Port)" `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort $Port | Out-Null
    Write-Host "[OK] 已创建防火墙规则 ($Port)" -ForegroundColor Green
} else {
    if (-not $rule.Enabled) { Enable-NetFirewallRule -Name $ruleName }
    Write-Host "[OK] 防火墙规则已存在并启用" -ForegroundColor Green
}
# 如果改了端口, 关掉旧的 22 规则避免暴露多余端口
if ($Port -ne 22) {
    $oldRule = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
    if ($oldRule) {
        Disable-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
        Write-Host "[OK] 已禁用旧的 22 端口规则" -ForegroundColor Yellow
    }
}

# ---------- 6. 重启 sshd ----------
Write-Host "`n=== 6. 重启 sshd ===" -ForegroundColor Cyan
Restart-Service sshd -Force
Start-Sleep -Seconds 2
Write-Host "sshd: $((Get-Service sshd).Status)"

# ---------- 7. 验证 ----------
Write-Host "`n=== 7. 验证 ===" -ForegroundColor Green

$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    Write-Host "[OK] 端口 $Port 正在监听 (PID: $($listen.OwningProcess | Select-Object -First 1))" -ForegroundColor Green
} else {
    Write-Host "[X] 端口 $Port 未监听, 检查 sshd" -ForegroundColor Red
}

Write-Host "`n本机信息 (客户端连接用):" -ForegroundColor Cyan
Write-Host "  主机名   : $env:COMPUTERNAME"
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown"} | Select-Object -ExpandProperty IPAddress -Unique
Write-Host "  IPv4     : $($ips -join ', ')"
Write-Host "  SSH 端口 : $Port"
Write-Host "  允许账户 : $AllowUser"
Write-Host "  连接命令 : ssh -p $Port $AllowUser@<WORKSTATION_IP>"

Write-Host "`n========== 完成 ==========" -ForegroundColor Green
if (-not $DisablePassword) {
    Write-Host "`n下一步 (重要!):" -ForegroundColor Yellow
    Write-Host "  1. 从客户端用密码连一次:  ssh -p $Port $AllowUser@<WORKSTATION_IP>" -ForegroundColor White
    Write-Host "  2. 按 ssh-client-guide.md 第2节配密钥免密" -ForegroundColor White
    Write-Host "  3. 配好密钥后回来执行:    .\setup-ssh-server.ps1 -DisablePassword" -ForegroundColor White
    Write-Host "     (彻底关闭密码认证, 公网必做!)" -ForegroundColor Red
} else {
    Write-Host "`n[OK] 密码认证已关闭, 现在仅密钥登录" -ForegroundColor Green
    Write-Host "测试: ssh -p $Port $AllowUser@<WORKSTATION_IP> (应免密直接进)" -ForegroundColor White
}

Write-Host "`n排错提示:" -ForegroundColor Yellow
Write-Host "  - 若客户端连不上: 国内 ISP 可能封 22, 试 .\setup-ssh-server.ps1 -Port 22222" -ForegroundColor White
Write-Host "  - 查看日志: Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 20" -ForegroundColor White
