# NJUPT Paper Access

一个面向南京邮电大学师生与研究人员的 Codex/Agent skill，用于：

- 通过 Crossref 和 OpenAlex 检索正式论文元数据。
- 从 DOI 自动识别出版社与稳定的后台全文端点。
- 下载开放获取论文，或使用已授权的官方 TDM/API。
- 对需要个人登录会话的订阅内容生成可审计的 `manual_required` 清单。
- 校验 PDF、按标题/DOI 命名、保留下载清单并支持断点续跑。

本项目不是南京邮电大学官方产品。

## 支持情况

| 平台 | 后台接入 | 状态 |
| --- | --- | --- |
| IEEE Xplore | DOI → article number → `stampPDF/getPDF.jsp` | 已实测 |
| Springer Nature | `content/pdf/{DOI}.pdf` | 已实测 |
| Nature | `{article-url}.pdf` | 已实测 |
| IOPscience | `/article/{DOI}/pdf` | 已实测 |
| Elsevier | Article Retrieval API | 已接入，需 API key/insttoken |
| Wiley | Wiley TDM API | 已接入，需 TDM token |
| ACM / T&F / Science / ACS | 官方接口或正常网页 | Cloudflare 防护，不做绕过 |
| CNKI | 正常认证界面 | 验证码不做自动化 |
| 万方 | 权限感知 gRPC-web | 不提供连续下载器 |

详细端点与实测说明见
[`njupt-paper-access/references/backend-routes.md`](njupt-paper-access/references/backend-routes.md)。

## 安装

要求 Windows、Python 3.10+，以及 Chrome 或 Edge。

```powershell
git clone https://github.com/Ivan-Huang42/njupt-paper-access.git "$HOME\Downloads\njupt-paper-access-source"
powershell -ExecutionPolicy Bypass -File "$HOME\Downloads\njupt-paper-access-source\njupt-paper-access\scripts\install.ps1"
```

安装后：

- 可移植技能：`%USERPROFILE%\.agents\skills\njupt-paper-access`
- Codex 全局入口：`%USERPROFILE%\.codex\skills\njupt-paper-access`

脚本不会复制或创建账号凭据。

## 使用

```powershell
$skill = "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1"

# 环境与路径检查
& $skill doctor

# 检索元数据
& $skill collect "safe multi-agent reinforcement learning" --limit 20 --output results.json

# 单篇明确指定的论文
& $skill download 10.1109/TAC.2021.3105491 --output-dir ".\papers"

# 开放获取/官方 TDM 批处理
& $skill batch --input results.json --output-dir ".\papers\batch"

# 浏览器备用入口
& $skill login
```

官方 API 凭据通过环境变量或操作系统密钥存储提供：

```text
ELSEVIER_API_KEY
ELSEVIER_INST_TOKEN
WILEY_TDM_TOKEN
```

设置 `NJUPT_PAPER_CONTACT_EMAIL` 可使用 OpenAlex polite pool。

## 使用边界

南京邮电大学图书馆明确禁止通过自动程序连续检索或下载订阅数据库内容。
因此本技能的 `batch` 仅自动处理：

- 开放获取论文。
- 已取得正式 TDM/API 权限的内容。

普通订阅内容会进入 `manifest.json` 的 `manual_required` 队列。请通过学校
认可的网络、VPN 和正常网页操作逐篇获取。

本项目不会：

- 保存或请求校园密码。
- 分享浏览器会话。
- 绕过 Cloudflare、验证码、付费墙或 DRM。
- 批量抓取 CNKI、万方等受订阅保护的数据库。

## 安全

不要把账号密码、Cookie、API key 或浏览器 profile 提交到仓库。参见
[`SECURITY.md`](SECURITY.md)。

## 开发检查

```powershell
python -m py_compile .\njupt-paper-access\scripts\njupt_paper.py
ruff check .
ruff format --check .
python .\njupt-paper-access\scripts\njupt_paper.py resolve 10.1109/TAC.2021.3105491
```

## 许可证

[MIT](LICENSE)
