# SSH 工作站免密配置指南

> 跨公网 SSH 连接 Windows 工作站, 用于 ComfyUI 模型同步。
> 本文档为通用指南, 实际部署时将 `<占位符>` 替换为你的真实值。

## 适用场景

- 笔记本 (内网) → 公网 → Windows 工作站
- 需要免密 SCP 传文件 (如 ComfyUI 模型同步)
- 替代不安全的 WinRM Basic 明文认证

## 网络拓扑

```
笔记本 (内网, 动态公网出口)
  └─ SSH 客户端 (Windows 自带 OpenSSH)
        │  公网 22 端口 (免密密钥认证)
        ▼
工作站 (公网 IP <WORKSTATION_IP>)
  ├─ SSH 服务端: OpenSSH Server
  ├─ 登录账户: <USERNAME> (Administrators 成员)
  └─ ComfyUI: < ComfyUI 路径>
```

## 服务端配置 (工作站)

运行 `scripts/setup-ssh-server.ps1` (管理员 PowerShell):

```powershell
# 首次配置 (临时开密码认证)
.\setup-ssh-server.ps1

# 自定义端口 (若 ISP 封 22)
.\setup-ssh-server.ps1 -Port 22222

# 配好密钥后禁用密码 (公网必做)
.\setup-ssh-server.ps1 -DisablePassword
```

关键 sshd_config (Match 块必须放最后):
```
Port 22
MaxAuthTries 3
LoginGraceTime 30
AllowUsers <USERNAME>
PubkeyAuthentication yes
PasswordAuthentication no
Subsystem sftp sftp-server.exe

Match Group administrators
    AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```

## 客户端配置 (笔记本)

1. 生成密钥:
   ```powershell
   ssh-keygen -t ed25519
   ```

2. 上传公钥 (Administrators 账户须放系统级文件):
   ```powershell
   $pub = Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub" -Raw
   ssh -p 22 <USERNAME>@<WORKSTATION_IP> "
     `$f = 'C:\ProgramData\ssh\administrators_authorized_keys'
     if (-not (Test-Path `$f)) { New-Item -ItemType File -Path `$f -Force | Out-Null }
     Add-Content -Path `$f -Value '$($pub.Trim())'
     icacls `$f /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F'
   "
   ```

3. 配置 ~/.ssh/config 别名:
   ```
   Host ws
       HostName <WORKSTATION_IP>
       Port 22
       User <USERNAME>
       IdentityFile ~/.ssh/id_ed25519
       ServerAliveInterval 60
   ```

## 模型同步集成

`sync_models.py` 支持 SCP 别名免密:
```powershell
python scripts/sync_models.py --src D:\models --dst ws:/e/ComfyUI/models
```

## 必踩坑 (6 个)

1. **PermitRootLogin**: Windows 不支持, 写入 → sshd 启动失败
2. **Match 块位置**: `Match Group administrators` 会作用到文件末尾, 全局指令不能写其后
3. **账户名 vs 家目录**: Windows 账户名和 profile 目录名可能不一致
4. **Administrators 公钥位置**: 必须放 `C:\ProgramData\ssh\administrators_authorized_keys`
5. **ACL 必须**: administrators_authorized_keys 只允许 Administrators+SYSTEM
6. **Invalid user**: OpenSSH 把密码错误显示为 Invalid user, 用 `runas` 测真实密码

## 诊断命令

```powershell
# sshd 配置语法检查 (无输出=通过)
& "C:\Windows\System32\OpenSSH\sshd.exe" -t

# 测端口连通
Test-NetConnection -ComputerName <WORKSTATION_IP> -Port 22

# 看 sshd 日志
Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 20
```
