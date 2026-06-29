# 📡 4G 短信转发系统 — 「短信快递员」

> *"你的验证码，我来送！"* — 某不知名 4G 模块留

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

## 🤔 这是个什么东西？

想象一下这个场景：

> 你有一张 SIM 卡插在某个犄角旮旯的 4G 模块里，专门用来收验证码。
> 但每次都要 SSH 进去看？或者爬过去拔卡插手机？
>
> 🙅 太 LOW 了。

**这个系统就是你的「短信快递员」** 🚀——

- 它帮你死守在 Linux 设备上盯着 4G 模块
- 来一条短信，立刻飞到你邮箱 📧
- 还能 Web 界面管理，深色模式护眼，手机也能看
- 支持多卡多模块，一条龙服务

```
  📱 验证码短信
       ⬇
  📡 4G 模块 (EC20/SIM7600...)
       ⬇ 
  🐍 Python 系统 (本项目)
       ⬇
  📧 你的邮箱 💌
```

---

## ✨ 功能拉满

| 功能 | 状态 | 卖个萌 |
|------|:----:|--------|
| 🎧 实时短信监听 | ✅ | 比你家猫还警觉 |
| 🔄 定时短信同步 | ✅ | 打死不丢一条短信 |
| 📧 邮件自动转发 | ✅ | SMTP/TLS/SSL 全支持 |
| 🖥️ Web 后台管理 | ✅ | 颜值即正义 |
| 🌙 深色/浅色模式 | ✅ | 深夜党福音 |
| 📱 响应式手机访问 | ✅ | 马桶上也能管理 |
| 🔌 多模块管理 | ✅ | USB 不够用？插满！ |
| 🧩 AT 驱动适配层 | ✅ | 管你移远还是华为 |
| 🛠️ AT 调试终端 | ✅ | 在线敲 AT，比串口助手香 |
| 💾 SQLite 数据库 | ✅ | 十万条短信不卡顿 |
| 🔐 Web 登录认证 | ✅ | 不是谁都能偷看的 |
| 📊 Chart.js 统计图表 | ✅ | 数据可视化，老板最爱 |
| 🔔 WebSocket 实时推送 | ✅ | 短信到了，页面秒弹 |
| 📤 导出 JSON/CSV | ✅ | 数据在手天下我有 |
| 🔁 自动重连 | ✅ | 断线？不存在 |
| 🗑️ 数据自动清理 | ✅ | 小磁盘也能放心跑 |
| 📦 配置导入/导出 | ✅ | 搬家一键搞定 |
| 🏥 数据库维护 | ✅ | VACUUM/备份/完整性检查 |
| 📝 完整日志系统 | ✅ | 每一行都有迹可循 |
| 🐳 Docker 部署 | 🚧 | 后续安排上 |
| 🤖 Bot 转发 (Telegram/钉钉/飞书) | 🚧 | 二期工程 |

---

## 📡 支持的 4G 模块

> "我不是针对谁，我是说在座的各位模块，都能跑"  
> — AT 适配层

| 品牌 | 型号 | 支持级别 | 备注 |
|------|------|:--------:|------|
| **Quectel 移远** 🥇 | EC20, EC25, EG25, EC200, EG91 | ⭐⭐⭐ 亲儿子 | 重点优化，QNWINFO 信号查询 |
| **SIMCom** 🥈 | SIM7600, A7600, SIM7000, SIM800 | ⭐⭐ 干儿子 | CNSMOD 特有指令适配 |
| **Huawei 华为** 🥉 | ME909, ME906, MU609 | ⭐⭐ 外甥 | ^SYSINFO/^HCSQ 已适配 |
| **其他兼容模块** | 任何支持标准 AT 指令的 | ⭐ 路人甲 | 自动走 Generic 驱动，能用 |

> 💡 **Pro Tip：** 买 EC20，求求了。这是测试最充分的，闭眼入。

---

## 🖥️ 系统要求

| 项目 | 最低配置 | 推荐配置 | 备注 |
|------|----------|----------|------|
| 🐍 Python | 3.11+ | 3.12+ | 别用 2.7，都 3026 年了 |
| 🐧 OS | Any Linux | Debian/Ubuntu | ARMv7 海思平台也可 |
| 🧠 RAM | 512MB | 1GB+ | 树莓派 Zero 都够 |
| 💿 磁盘 | 100MB | 1GB+ | 留给短信的「别墅」 |
| 📡 4G 模块 | 1 个 | N 个 | EC20 淘宝 40 块包邮 |
| 🔌 USB 口 | 1 个 | 看你有多少模块 | Hub 不够？再加一个 |

---

## 🚀 快速开始 — 「5 分钟起飞」

### 第一步：克隆 & 安装 📦

```bash
# 进入项目目录
cd project

# 安装依赖（建议用 venv）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 此时去泡杯咖啡 ☕，下载很快的
```

### 第二步：配置 🔧

编辑两个配置文件：

**`config/config.json`** — 系统设置

```json
{
  "serial": {
    "default_port": "/dev/ttyUSB2",   // 👈 改成你 4G 模块的串口
    "baudrate": 115200,                // 一般不用改
    "scan_ports": ["/dev/ttyUSB*"]     // 自动扫描哪些串口
  },
  "web_auth": {
    "username": "admin",
    "password_hash": "..."             // 首次启动用 admin/admin
  }
}
```

**`config/mail.json`** — 邮件转发设置

```json
{
  "enabled": true,
  "smtp_server": "smtp.qq.com",        // 👈 QQ邮箱/Gmail/163 随便
  "smtp_port": 587,
  "username": "你的邮箱@qq.com",
  "password": "你的SMTP授权码",         // ⚠️ 不是QQ密码！是授权码！
  "from_email": "你的邮箱@qq.com",
  "recipients": [
    "收件人1@qq.com",
    "收件人2@gmail.com"
  ],
  "subject_template": "📱 {{module_name}} 收到短信",
  "body_template": "<h2>新短信来啦</h2><p>号码: {{phone}}</p><p>{{content}}</p>"
}
```

> ⚠️ **重要！** QQ 邮箱/163 邮箱的 SMTP 密码是**授权码**，不是登录密码！  
> 去邮箱设置 → 账户 → POP3/SMTP → 生成授权码
> 
> Gmail 用户需要开启「两步验证」后使用「应用专用密码」

### 第三步：启动 🎬

```bash
python app.py

# 输出类似：
# [INFO] root: 数据库表已初始化
# [INFO] root: 扫描到 2 个串口: ['/dev/ttyUSB2', '/dev/ttyUSB3']
# [INFO] root: 自动发现模块: /dev/ttyUSB2 -> Quectel EC20
# [INFO] root: 启动 Web 服务器: 0.0.0.0:5000
```

### 第四步：打开浏览器 🌐

```
http://你的设备IP:5000
```

默认账号：**`admin`** / **`admin`**

> 🔐 进后台第一件事：去「系统设置」改密码！别等被室友偷看短信再后悔！

---

## 🖼️ Web 界面一览

```
┌──────────────────────────────────────────────────┐
│ 📡 4G SMS Forward System                  🌙 📴  │
├──────────┬───────────────────────────────────────┤
│ 🏠 首页   │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐    │
│ 💬 短信   │  │ 今日 │ │ 已转 │ │ 在线 │ │ CPU │    │
│ ✉️ 发送   │  │  12  │ │  12  │ │   2  │ │ 15% │    │
│ 🖥️ 模块   │  └─────┘ └─────┘ └─────┘ └─────┘    │
│ ⌨️ AT调试 │  ┌──────────────────────────┐       │
│ 📧 邮件   │  │  📊 短信趋势图 (Chart.js) │       │
│ ⚙️ 设置   │  │  📈 系统资源监控          │       │
│ 📋 日志   │  │  🖥️ 模块实时状态卡片      │       │
│ 🗄️ 数据库 │  └──────────────────────────┘       │
└──────────┴───────────────────────────────────────┘
```

### 各页面功能速览

| 页面 | 图标 | 能干啥 |
|------|:----:|--------|
| **仪表盘** | 🏠 | 一看就懂的系统概览：模块状态、CPU/内存、短信统计、实时图表 |
| **短信记录** | 💬 | 所有短信表格展示、搜索/分页/筛选、批量操作、导出 JSON/CSV |
| **发送短信** | ✉️ | 选择模块 → 输入号码 → 写内容 → 点击发送 → 等 OK |
| **模块管理** | 🖥️ | 扫描串口、自动发现、修改备注、重连、禁用模块 |
| **AT 调试** | ⌨️ | 像串口助手一样敲 AT 指令，有快捷按钮，有历史记录 |
| **邮件配置** | 📧 | SMTP 设置、收件人管理、邮件模板编辑、**测试发送按钮** |
| **系统设置** | ⚙️ | 串口参数、短信同步、日志级别、配置导入导出 |
| **日志** | 📋 | 系统日志查看、按级别过滤、搜索、下载、清空 |
| **数据库** | 🗄️ | VACUUM 优化、完整性检查、备份/恢复、按天数/数量清理 |

---

## 🧩 架构设计 — 「这代码写得还行」

```
┌─────────────────────────────────────────────────┐
│                    app.py                        │
│            (Flask + SocketIO 主进程)              │
│        路由 / API / 认证 / WebSocket              │
└──────────┬──────────────┬───────────────────────┘
           │              │
    ┌──────▼──────┐ ┌─────▼──────────┐
    │  sms_engine │ │ mail_forwarder │
    │  短信引擎    │ │   邮件转发器    │
    │ 接收/同步/去重│ │ SMTP/TLS/模板  │
    └──────┬──────┘ └────────────────┘
           │
    ┌──────▼──────────┐
    │  modem_manager  │   ← 多模块管理器（核心调度）
    │  扫描/连接/监控   │
    └──┬──┬──┬───────┘
       │  │  │
  ┌────▼──▼──▼────┐
  │  modem/drivers │      ← AT 适配层
  │ base / quectel │
  │ simcom / huawei│
  └───────┬────────┘
          │
    ┌─────▼──────┐
    │   pySerial  │       ← 串口通信
    │  /dev/tty*  │
    └────────────┘

  ┌──────────────┐
  │   SQLite DB  │        ← 唯一数据源
  │   data/sms.db │
  └──────────────┘
```

### 模块职责

| 模块 | 文件 | 一句话总结 |
|------|------|-----------|
| **主入口** | `app.py` | Flask 全家桶：路由、API、SocketIO、认证 |
| **数据库层** | `database/` | SQLAlchemy ORM，5 张表，增删改查全封装 |
| **AT 驱动** | `modem/base.py` | 通用 AT 指令封装，所有驱动之爹 |
| **移远驱动** | `modem/quectel.py` | EC20 专属 buff：QNWINFO、QCSQ、QCELLLOC |
| **SIMCom 驱动** | `modem/simcom.py` | SIM7600 专用：CNSMOD 网络制式查询 |
| **华为驱动** | `modem/huawei.py` | 华为特色：^SYSINFO、^HCSQ 信号查询 |
| **模块管理** | `modem/manager.py` | 多模块生命周期管理，热插拔检测，自动重连 |
| **短信引擎** | `web/sms_engine.py` | 实时接收 + 定时同步 + SHA256 去重 |
| **邮件转发** | `web/mail_forwarder.py` | SMTP → 模板渲染 → 发送 → 写日志 |
| **Web 通知** | `web/notifier.py` | SocketIO 推送：新短信、状态变化、报警 |
| **配置管理** | `utils/config_manager.py` | JSON 配置读写，原子保存，线程安全 |
| **辅助函数** | `utils/helpers.py` | UCS2/GSM7 解码、CSQ 换算、哈希生成 |

---

## 📧 邮件模板变量大全

邮件标题和正文支持以下变量，用 `{{变量名}}` 即可：

| 变量 | 含义 | 示例值 |
|------|------|--------|
| `{{phone}}` | 📱 来源号码 | `+8613812345678` |
| `{{content}}` | 💬 短信内容 | `您的验证码：123456，打死不要告诉别人` |
| `{{time}}` | 🕐 接收时间 | `2026-06-30 18:20:35` |
| `{{imei}}` | 🆔 模块 IMEI | `860123456789012` |
| `{{carrier}}` | 📶 运营商 | `中国移动` |
| `{{operator}}` | 📶 运营商（同上） | `中国联通` |
| `{{signal}}` | 📊 信号强度 | `85%` |
| `{{module_name}}` | 🏷️ 模块备注 | `客厅EC20` |
| `{{module_port}}` | 🔌 模块端口 | `/dev/ttyUSB2` |
| `{{module_model}}` | 📡 模块型号 | `EC20` |

**示例邮件模板：**

```html
<h2>📱 来短信啦！</h2>
<table border="1" cellpadding="8">
  <tr><td>📱 号码</td><td>{{phone}}</td></tr>
  <tr><td>🕐 时间</td><td>{{time}}</td></tr>
  <tr><td>💬 内容</td><td>{{content}}</td></tr>
  <tr><td>📡 来源</td><td>{{module_name}} ({{module_model}})</td></tr>
  <tr><td>📶 信号</td><td>{{signal}}</td></tr>
  <tr><td>🏢 运营商</td><td>{{operator}}</td></tr>
</table>
<p><small>由 {{module_name}} 通过 4G 短信转发系统自动发送</small></p>
```

---

## 🐳 部署指南

### 方式一：直接跑（开发/测试）

```bash
python app.py
# Ctrl+C 停止
```

### 方式二：Systemd 服务（生产环境）👍

```bash
# 1. 把项目放到 /opt/
sudo cp -r project /opt/4g-sms-system

# 2. 安装服务文件
sudo cp /opt/4g-sms-system/4g-sms-system.service /etc/systemd/system/

# 3. 启动
sudo systemctl daemon-reload
sudo systemctl enable 4g-sms-system    # 开机自启
sudo systemctl start 4g-sms-system     # 立即启动

# 4. 看状态
sudo systemctl status 4g-sms-system
# 日志
sudo journalctl -u 4g-sms-system -f     # 实时追踪
```

### 方式三：screen / tmux（简单粗暴）

```bash
screen -S sms
cd /opt/4g-sms-system && python app.py
# Ctrl+A D 断开
# screen -r sms 恢复
```

---

## 🔐 安全备忘录

> 🚨 **安全无小事，短信被偷看就尴尬了！**

- [ ] **改默认密码**：`admin/admin` → 换成强密码 👈 **最优先！**
- [ ] **配置文件权限**：`chmod 600 config/*.json`
- [ ] **SMTP 用授权码**：别把邮箱登录密码写配置文件里
- [ ] **加 HTTPS**：用 Nginx/Caddy 反代 + Let's Encrypt
- [ ] **防火墙**：只开放必要端口（5000 别暴露到公网）
- [ ] **定期备份**：去「数据库维护」页面点一下备份
- [ ] **改 Flask SECRET_KEY**：`config/config.json` 里生成个随机的

```
🔑 快速生成随机密钥：
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📁 完整目录树

```
project/
│
├── 📄 app.py                      # 🎯 主程序入口（820+ 行）
├── 📄 requirements.txt            # 📦 Python 依赖清单
├── 📄 4g-sms-system.service       # ⚙️  Systemd 服务文件
├── 📄 README.md                   # 📖 你正在看的这个
│
├── 📁 config/
│   ├── 📄 config.json             # ⚙️  系统配置（串口/短信/日志/认证）
│   └── 📄 mail.json               # 📧 邮件 SMTP 配置
│
├── 📁 database/
│   ├── 📄 __init__.py             # 🏷️  模块导出
│   ├── 📄 database.py             # 🗄️  数据库管理器（VACUUM/备份/清理）
│   └── 📄 models.py               # 📊  ORM 数据模型（5 张表）
│
├── 📁 modem/
│   ├── 📄 __init__.py             # 🏷️  驱动导出
│   ├── 📄 base.py                 # 🧬  通用 AT 驱动基类（400+ 行）
│   ├── 📄 quectel.py              # 📡  移远 EC20/EC25 专用驱动
│   ├── 📄 simcom.py               # 📡  SIMCom SIM7600 专用驱动
│   ├── 📄 huawei.py               # 📡  华为 ME909 专用驱动
│   └── 📄 manager.py              # 🎛️  多模块管理器（热插拔/自动发现）
│
├── 📁 web/
│   ├── 📄 __init__.py             # 🏷️  业务模块导出
│   ├── 📄 sms_engine.py           # ⚡ 短信处理引擎（接收/同步/去重）
│   ├── 📄 mail_forwarder.py       # 📧 邮件转发器（SMTP + 模板）
│   └── 📄 notifier.py             # 🔔 WebSocket 实时推送
│
├── 📁 utils/
│   ├── 📄 __init__.py             # 🏷️  工具模块导出
│   ├── 📄 config_manager.py       # 🔧 配置管理器（原子保存/线程安全）
│   ├── 📄 logger.py               # 📝 日志系统（文件 + 数据库双写）
│   └── 📄 helpers.py              # 🛠️  辅助函数（UCS2解码/CSQ换算/哈希）
│
├── 📁 templates/                   # 🎨 Jinja2 模板
│   ├── 📄 base.html               # 🏗️  基础布局（侧边栏/主题/WebSocket）
│   ├── 📄 login.html              # 🔐 登录页
│   ├── 📄 index.html              # 🏠 仪表盘（Chart.js 图表）
│   ├── 📄 sms.html                # 💬 短信记录（搜索/分页/批量）
│   ├── 📄 send.html               # ✉️  发送短信
│   ├── 📄 modems.html             # 🖥️  模块管理
│   ├── 📄 at.html                 # ⌨️  AT 调试终端
│   ├── 📄 mail.html               # 📧 邮件配置 + 测试
│   ├── 📄 settings.html           # ⚙️  系统设置 + 导入导出
│   ├── 📄 logs.html               # 📋 日志查看
│   └── 📄 database.html           # 🗄️  数据库维护
│
├── 📁 static/                      # 🎨 静态资源
│   ├── 📁 css/
│   └── 📁 js/
│
└── 📁 data/                        # 💾 运行时数据（自动生成）
    ├── 📄 sms.db                   # 🗄️  SQLite 数据库
    └── 📁 log/
        └── 📄 system.log           # 📝 系统日志文件
```

---

## 🐛 常见问题 FAQ

<details>
<summary><b>Q: 串口打不开 / Permission denied？</b></summary>

```bash
# 把自己加入 dialout 组
sudo usermod -a -G dialout $USER
# 重新登录生效

# 或者直接给权限（暴力但有效）
sudo chmod 666 /dev/ttyUSB*
```
</details>

<details>
<summary><b>Q: 模块不响应 AT 指令？</b></summary>

1. 确认串口号对不对：`ls /dev/ttyUSB*`
2. 用 `screen` 测试：`screen /dev/ttyUSB2 115200` 然后敲 `AT` 回车
3. 查看 `dmesg | grep tty` 看驱动有没有加载
4. EC20 可能需要先 `echo -ne "AT\r\n" > /dev/ttyUSB2` 唤醒
</details>

<details>
<summary><b>Q: 邮件发不出去？</b></summary>

1. 🚨 99% 是因为密码填了登录密码而不是 **SMTP 授权码**
2. QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码
3. 去「邮件配置」页面点「测试发送」排查
4. 检查服务器端口：QQ 邮箱 587(TLS) / 465(SSL)，Gmail 587(TLS)
</details>

<details>
<summary><b>Q: 收到短信是乱码？</b></summary>

系统已支持 UCS2 和 GSM7 编码自动解码。如果还乱码，可能是：
- 发送方用了奇怪的编码 → AT 调试页面手动查
- 去「AT 调试」执行 `AT+CMGL="ALL"` 看原始数据
- 提 Issue 把原始 hex 贴上来
</details>

<details>
<summary><b>Q: 内存越用越多？</b></summary>

1. 去「数据库维护」页面点「VACUUM 优化」
2. 设置「最大保留条数」让系统自动清理
3. SQLite 本身内存占用很小，10 万条短信大约 50MB
4. 如果还大，可能是有其他进程吃内存，`htop` 查一下
</details>

<details>
<summary><b>Q: 树莓派能跑吗？</b></summary>

能！树莓派 3B/4B/Zero 2W 都测过。ARMv7 海思平台也行（就是你手里的设备）。内存占用 < 100MB，CPU 基本不占。
</details>

<details>
<summary><b>Q: 怎么备份数据？</b></summary>

三种方式：
1. 🖱️ Web → 数据库维护 → 点「一键备份」
2. 📋 命令行：`cp data/sms.db data/sms.db.backup`
3. 🕐 写个 cron 定时任务自动备份
</details>

---

## 🎯 开发路线图

```
✅ v1.0 — 已完成
  ├── 多模块管理
  ├── 实时监听 + 定时同步
  ├── 邮件转发 + 模板变量
  ├── Web UI（9 个页面）
  ├── AT 驱动适配层（3 个品牌）
  ├── AT 调试终端
  ├── SQLite 数据库
  ├── WebSocket 实时推送
  └── Systemd 服务部署

🚧 v1.1 — 计划中
  ├── Webhook 转发
  ├── Telegram Bot 转发
  ├── 钉钉/飞书/企微机器人
  ├── REST API 开放接口
  ├── 短信关键字过滤
  ├── 黑白名单
  └── Docker 镜像

🔮 v2.0 — 未来
  ├── 短信统计报表
  ├── Grafana 集成
  ├── PostgreSQL/MySQL 支持
  ├── 多用户权限管理
  └── 短信自动回复规则
```

---

## 🤝 贡献

Bug 反馈、功能建议、PR 都欢迎！

如果你手上有什么奇怪的 4G 模块跑不起来，去 AT 调试页面截个图提 Issue，我来适配驱动。

---

## 📜 许可证

MIT License — 随便用，随便改，随便拿去赚钱，不用谢。

---

<p align="center">
  <b>Made with 🐍 + ☕ + 😤</b>
  <br>
  <sub>「深夜调试 AT 指令的痛，懂的都懂」</sub>
</p>
