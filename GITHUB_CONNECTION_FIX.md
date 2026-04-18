# GitHub 连接问题解决方案

## 🔴 问题描述
```
fatal: unable to access 'https://github.com/...': Failed to connect to github.com port 443
```

这是网络连接问题，通常是因为：
- 网络限制或防火墙阻止
- 需要代理才能访问 GitHub
- DNS 解析问题

## ✅ 解决方案（按推荐顺序）

### 方案 1: 使用 SSH 代替 HTTPS（最推荐）

SSH 通常比 HTTPS 更稳定，特别是在网络受限的环境中。

#### 步骤 1: 检查是否已有 SSH 密钥
```bash
ls ~/.ssh
```
如果看到 `id_rsa` 和 `id_rsa.pub` 或 `id_ed25519` 和 `id_ed25519.pub`，说明已有密钥。

#### 步骤 2: 如果没有密钥，生成新的 SSH 密钥
```bash
ssh-keygen -t ed25519 -C "547280811@qq.com"
```
按 Enter 使用默认路径，可以设置密码（可选）。

#### 步骤 3: 复制公钥
```bash
cat ~/.ssh/id_ed25519.pub
```
或者（如果使用 RSA）：
```bash
cat ~/.ssh/id_rsa.pub
```

#### 步骤 4: 将公钥添加到 GitHub
1. 复制刚才输出的公钥内容
2. 访问 https://github.com/settings/keys
3. 点击 "New SSH key"
4. 粘贴公钥，保存

#### 步骤 5: 修改远程仓库地址为 SSH
```bash
git remote set-url origin git@github.com:MAydedie/create_graph.git
```

#### 步骤 6: 测试连接
```bash
ssh -T git@github.com
```
如果看到 "Hi MAydedie! You've successfully authenticated..." 说明成功。

#### 步骤 7: 推送代码
```bash
git push -u origin main
```

---

### 方案 2: 配置 HTTP/HTTPS 代理

如果你有可用的代理（VPN、科学上网工具等），可以配置 Git 使用代理。

#### 查找代理端口
通常代理工具会在本地开启一个端口，常见的有：
- 127.0.0.1:7890
- 127.0.0.1:1080
- 127.0.0.1:8080

#### 配置 Git 代理（临时，仅当前仓库）
```bash
# 设置 HTTP 代理（替换为你的代理地址和端口）
git config http.proxy http://127.0.0.1:7890
git config https.proxy http://127.0.0.1:7890

# 或者使用 socks5 代理
git config http.proxy socks5://127.0.0.1:1080
git config https.proxy socks5://127.0.0.1:1080
```

#### 配置 Git 代理（全局，所有仓库）
```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

#### 取消代理（如果不需要了）
```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
```

---

### 方案 3: 增加超时时间和重试次数

```bash
git config --global http.postBuffer 524288000
git config --global http.lowSpeedLimit 0
git config --global http.lowSpeedTime 999999
```

---

### 方案 4: 使用 GitHub 镜像（不推荐，仅临时方案）

如果以上方法都不行，可以考虑使用 GitHub 镜像，但这不是长期解决方案。

---

## 🚀 快速执行脚本

我已经为你准备了自动化脚本，你可以选择：

### 选项 A: 切换到 SSH（推荐）
运行以下命令，我会帮你切换到 SSH 方式。

### 选项 B: 配置代理
如果你有代理，告诉我代理地址和端口，我可以帮你配置。

---

## 📝 当前状态

- ✅ 远程仓库已配置: `https://github.com/MAydedie/create_graph.git`
- ❌ 网络连接失败
- ⚠️ 需要选择上述方案之一

---

## 💡 建议

**最推荐的方案是使用 SSH**，因为：
1. 更稳定可靠
2. 不需要每次输入密码
3. 不受 HTTPS 端口限制影响

如果你需要我帮你执行某个方案，请告诉我你的选择！





































