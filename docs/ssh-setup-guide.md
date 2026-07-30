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

## 进阶：VS Code Remote SSH（推荐远程开发方式）

VS Code Remote SSH 通过 VS Code Server 在工作站上运行终端，其进程不受 SSH session 生命周期限制。这是唯一能从远程直接启动持久后台进程的方式。

```bash
# 笔记本 → 工作站 VS Code 远程窗口
code --remote ssh-remote+<ALIAS> /path/to/ComfyUI
```

**与纯 SSH 的区别**：

| 操作 | 纯 SSH 终端 | VS Code Remote 终端 |
|------|------------|-------------------|
| 启动持久进程 | 进程随会话断开被 kill | 进程由 VS Code Server 托管，持久存活 |
| SCP 传文件 | 正常 | 仍需 ssh/scp 命令 |
| 适用场景 | 紧急查看状态、传文件 | 日常开发、模型管理、持久后台服务 |

## 进阶：LLM 模型加载 (llama-server)

工作站可运行 llama-server 提供 OpenAI 兼容 API，用于智能提示增强或自动化。

**方式 A：VS Code Remote 终端（推荐）** — 进程持久加载

```bash
python scripts/llm_manager.py load 35b
python scripts/llm_manager.py status
```

**方式 B：LM Studio GUI（最稳定）** — 可视化加载

1. 打开 LM Studio → 选择模型 → 启动 Server（端口 1234）
2. 框架自动代理 `/v1` 路由到 LLM API

**检测机制**：llm_manager 自动识别三环境：
- `TERM_PROGRAM=vscode` → 直接启动（进程持久）
- `SSH_CLIENT/SSH_TTY` → 生成 `.bat`（双击运行）
- 本地终端 → 直接启动
