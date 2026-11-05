# 在 DSH 桌面端安装「求职作战包」插件

> 适用版本：DSH 桌面端 **0.2.1-rc.5**（`@deepseek-ai/dsh-desktop` 0.2.1-rc.5，安装包 FileVersion `0.2.1-rc.5`）
> 本文件记录的是**本机实测**的路径与命令，不是示意。换机器时先把第 1 节的路径核对一遍。

---

## 1. 本机实际位置（实测）

| 项 | 实际值 |
|---|---|
| DSH 可执行文件 | `C:\Users\22334\AppData\Local\Programs\DeepSeek Harness\DeepSeek Harness.exe` |
| DSH 用户目录 | `C:\Users\22334\.dsh` |
| DSH 命令行入口 | `C:\Users\22334\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd` |
| desktop profile | `C:\Users\22334\.dsh\profiles\desktop` |
| **插件源目录（权威副本）** | `C:\Users\22334\.dsh\plugins\dsh-job-skill-plugin` |
| **插件实际加载位置** | `C:\Users\22334\.dsh\profiles\desktop\node_modules\dsh-job-skill-plugin`（pnpm 从源目录复制的副本，DSH 从这里加载） |
| 插件加载自证日志 | `C:\Users\22334\.dsh\profiles\desktop\node_modules\dsh-job-skill-plugin\load.log` |
| sidecar | `C:\Users\22334\Desktop\dsh-job-copilot-codex-pack\starter\sidecar`，监听 `127.0.0.1:8000` |
| 报告输出目录 | `C:\Users\22334\Desktop\dsh-job-copilot-codex-pack\reports` |

> 注意：pnpm 的 `file:` 依赖是**复制**，不是软链。改了源目录后要重新 `install` 才会同步到 `node_modules`，否则 DSH 加载的还是旧代码。

---

## 2. 插件包含什么

| 类型 | 名称 | 说明 |
|---|---|---|
| 工具 | `resume-structurer` | 简历 → 结构化 JSON（带 `exp_01…` 证据 ID） |
| 工具 | `company-recon` | 公司背调（basic / deep，deep 先预估再确认） |
| 工具 | `jd-decoder` | JD → `jd_01…` 要求 ID |
| Skill | `job-fit-orchestrator` | 编排层：固定执行顺序 + 降级话术 + 红线 |
| 命令 | `job-fit` | 一条命令跑完「简历 + JD + 公司 → 卡片 + Markdown」（v1.0.1 起已在斜杠菜单中，见第 6 节） |

插件入口是 `host.mjs`（Cordis 插件：`export const name` / `export function apply`），它把 `dist/src` 里已有的 3 个工具原样注册给 DSH，**没有改任何工具签名、参数或超时**。

---

## 3. 首次安装（本机已执行过，此处为可复现步骤）

```powershell
# 0) 先完全退出 DSH，否则 pnpm 会被文件锁挡住（EPERM: lightningcss-*）
taskkill /F /IM "DeepSeek Harness.exe"

# 1) 仓库里的插件构建一份
cd C:\Users\22334\Desktop\dsh-job-copilot-codex-pack\starter\dsh-plugin
npm run build

# 2) 复制到 DSH 插件目录
#    package.json / host.mjs / cordis.patch.yml / dist / src\skill
xcopy /E /I /Y . "%USERPROFILE%\.dsh\plugins\dsh-job-skill-plugin"

# 3) 用 DSH 官方 CLI 装进 desktop profile（等价于 pnpm add）
"C:\Users\22334\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd" ^
  plugin --profile desktop add "file:../../plugins/dsh-job-skill-plugin"

# 4) 登记到 bundle 列表（否则依赖装了也不会被加载）
#    编辑 %USERPROFILE%\.dsh\profiles\desktop\package.json
#    在 dsh.profile.bundles 数组末尾加一项 "dsh-job-skill-plugin"

# 5) 启动 DSH
```

第 4 步也可以用脚本做（本机当时就是这么做的）：

```powershell
python -c "import json,os;p=os.path.expanduser('~/.dsh/profiles/desktop/package.json');d=json.load(open(p,encoding='utf-8'));b=d['dsh']['profile']['bundles'];b.append('dsh-job-skill-plugin') if 'dsh-job-skill-plugin' not in b else None;json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)"
```

**改过源码后一定要重新装**：pnpm 的 `file:` 依赖是硬链接缓存，光覆盖源目录、`dsh plugin --profile desktop install` 也可能复用 `node_modules` 里的旧副本（本机就踩到过：源目录已是新 `host.mjs`，profile 里还是 13:49 的旧版）。可靠做法是把插件 `package.json` 的版本号 +1、删掉 `profiles\desktop\node_modules\dsh-job-skill-plugin` 再 install，装完核对 `node_modules` 里那份的文件时间与内容。

**装没装上怎么验**：启动 DSH 后看 `load.log`，有当次时间戳、三个工具名、以及 `cmdcheck` 行即为加载与命令注册都成功：

```text
2026-11-05T06:23:34.256Z	plugin=dsh-job-skill-plugin	tools=resume-structurer,company-recon,jd-decoder	sidecar=http://localhost:8000
2026-11-05T06:23:34.618Z	cmdcheck	name=job-fit	registered=/feedback,/job-fit
```

`load.log` 写在**实际被加载的那份副本**目录下（`profiles\desktop\node_modules\dsh-job-skill-plugin\`），不是源目录。

---

## 4. sidecar 启动与重启

### 4.1 启动（Mock 模式，默认，不花钱）

```powershell
cd C:\Users\22334\Desktop\dsh-job-copilot-codex-pack\starter\sidecar
$env:APP_MODE = "mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8000/health
# {"status":"ok","version":"1.0.0","mode":"mock","degraded_modules":[],"cache_days":7}
```

> `--noproxy "*"` 不能省：本机设了 `HTTP_PROXY=http://127.0.0.1:49446`，不加这个参数访问 127.0.0.1 会被代理拦成 **502**，看起来像"服务没起来"，其实是代理返回的。

### 4.2 每次开机/重启后的顺序

1. 开 DSH 桌面端（插件会自动加载，不需要点任何按钮）。
2. 开一个终端，按 4.1 启动 sidecar（**必须先起 sidecar**，否则工具调用会报"sidecar 不可达"）。
3. 回到 DSH，新建会话即可用。

顺序反了也能救：sidecar 起来后不需要重启 DSH，下一条工具调用会自动连上。

### 4.3 想让 sidecar 常驻

本机没有配 systemd/服务，简单做法是开一个固定终端窗口跑 4.1 的命令并最小化。关掉终端 sidecar 就停，工具会立刻开始报连接失败。

---

## 5. 常见问题

### 5.1 DSH 里看不到插件 / `load.log` 没有新行

按顺序查：

1. **bundle 有没有登记**：`%USERPROFILE%\.dsh\profiles\desktop\package.json` 的 `dsh.profile.bundles` 里有没有 `dsh-job-skill-plugin`。只有依赖没有 bundle，DSH 不会加载。
2. **依赖装了没有**：`dsh plugin --profile desktop list` 里能不能看到 `dsh-job-skill-plugin`。
3. **入口对不对**：`node_modules\dsh-job-skill-plugin\package.json` 的 `main` 必须是 `./host.mjs`，`dsh.bundle.patch` 必须指向 `./cordis.patch.yml`。
4. **代码是不是旧的**：pnpm 的 `file:` 是复制，改完源目录要重新 `install`。
5. **启动日志**：DSH 的启动输出里有 `dsh web: http://127.0.0.1:<port>/?token=...`，插件报错通常只出现在窗口控制台，`load.log` 没新行基本等于没加载。

### 5.2 sidecar 连不上

```powershell
# 1) 端口有没有人监听
netstat -ano | findstr ":8000"
# 2) 健康检查（一定要绕开代理）
curl.exe --noproxy "*" http://127.0.0.1:8000/health
# 3) 看 sidecar 窗口有没有 traceback
```

如果 `curl` 返回 502 而不是连接失败，是代理干的，不是 sidecar 没起。

### 5.3 端口 8000 被占

```powershell
netstat -ano | findstr ":8000"     # 最后一列是 PID
tasklist /FI "PID eq <PID>"
```

换端口启动 sidecar：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

但插件默认连 8000，要同步改环境变量（**在启动 DSH 的环境里设**，不是在 sidecar 里）：

```powershell
$env:SIDECAR_BASE_URL = "http://127.0.0.1:8010"
```

`load.log` 里会记下当时用的地址，可据此确认插件连的是哪个端口。

### 5.4 `dsh plugin --profile desktop add` 报 `EPERM: operation not permitted, rename ... lightningcss-*`

DSH 正在运行，文件被占。完全退出 DSH 再执行，执行完 `dsh plugin --profile desktop install` 补齐依赖。

### 5.5 从终端启动 DSH 一闪而过、进程立刻消失

检查当前 shell 有没有 `ELECTRON_RUN_AS_NODE=1`。有的话 Electron 会按 Node 跑，启动即退出。启动前清掉：

```powershell
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
Remove-Item Env:NODE_OPTIONS -ErrorAction SilentlyContinue
& "$env:LOCALAPPDATA\Programs\DeepSeek Harness\DeepSeek Harness.exe"
```

---

## 6. 已知限制（本机实测结论）

1. **`/job-fit` 命令（v1.0.1 已修复）**。第一轮实测它不在斜杠菜单里，根因不是协议也不是 bundle 登记：**命令对象写成了 `execute`，而 `@deepseek-ai/dsh-commands` 的 `normalizeDefinition` 要求 `handler` 必须是函数**，注册时直接抛 `TypeError`，异常被 `ctx.inject(['commands'], ...)` 回调吞掉，命令从未进注册表。改成官方 `/goal` 的形状（`definitionId` / `name` / `description` / `input.hint` / `handler`），并加了注册自证与回归测试后，DSH 桌面端 `/job` 过滤下同时显示「指令 `job-fit`」和「技能 `job-fit-orchestrator`」。证据见 `docs/evidence/dsh-desktop-slash-menu-crop.png`。
   - 注册表自证：插件目录下 `load.log` 的 `cmdcheck name=job-fit registered=/feedback,/job-fit`。
   - 回归测试：`tests/host-command.test.ts` 照抄 dsh-commands 的校验规则，`npm test` 从 28 涨到 30 全绿，防止 `execute` 这个坑回来。
   - 命令本身也实测跑通：`/job-fit --resume … --jd … --company … --out …` 会调 `/v1/analysis` 并落盘；DSH 把斜杠命令的结果写成日志事件、不在对话流里常驻显示，别误判成没执行，看 sidecar 日志和导出文件即可（本次为 `analysis=8e519787b088` 与 `reports\…-327e987b.md`）。
2. **桌面窗口输入要绕开中文输入法**。`SendInput` / `keybd_event` 直接敲字母会被 IME 拦成候选词（底部弹「job 基本 / 3 寄偶比」）。可用做法是：`SetForegroundWindow` / `SwitchToThisWindow` 把 DSH 置前 → 点击输入框 → 用 `win32clipboard` 塞 Unicode 文本 → `Ctrl+V` 粘贴 → `Enter` 发送。DSH 的 CDP 里只有 `dsh://host` 一个 Node realm target，没有渲染进程 DOM，所以桌面窗口不能靠 CDP 注入，只能走原生输入。
3. **报告正文一律由 sidecar 生成并落盘（v1.0.1 已在 skill 里写死）**。第一轮 agent 自己写了一份稿，`evidence_ref` 为 0、没有声明句，作废。现在 skill 强制：三个工具调完后必须 `POST /v1/analysis` → `POST /v1/report/export`（由 sidecar 写文件，agent 不许碰 `write`）→ 四条核对（与服务原文哈希一致、声明句、`evidence_ref` 数、Mock 标注）全过才算这一轮通过。实测 agent 确实按这个顺序执行，追问时只读报告文件、不重跑生成器。
4. **`out_dir` 相对路径按 sidecar 的工作目录解析**。skill 里写的是 `"out_dir":"reports"`，sidecar 从 `starter/sidecar` 启动，所以文件落在 `starter/sidecar/reports/`。想固定落点就给绝对路径（`/job-fit --out "C:/…/reports"` 就是这么做的）。两处都是真报告，只是路径不同；`starter/sidecar/reports/` 是运行时产物目录，未纳入版本管理，仓库里留的示例报告在根目录 `reports/`。

---

## 7. 停用与卸载

### 7.1 临时停用（保留文件）

编辑 `%USERPROFILE%\.dsh\profiles\desktop\package.json`，把 `dsh.profile.bundles` 里的 `dsh-job-skill-plugin` 删掉，重启 DSH。

### 7.2 彻底卸载

```powershell
# 1) 退出 DSH
taskkill /F /IM "DeepSeek Harness.exe"

# 2) 从 profile 移除依赖
"C:\Users\22334\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd" ^
  plugin --profile desktop remove dsh-job-skill-plugin

# 3) 同时从 bundle 列表删掉 "dsh-job-skill-plugin"

# 4) 删插件目录（源目录 + 复制副本）
rmdir /S /Q "%USERPROFILE%\.dsh\plugins\dsh-job-skill-plugin"
```

`node_modules` 下的副本由 pnpm 管，`remove` 之后会一起清掉；没清干净就手动删 `%USERPROFILE%\.dsh\profiles\desktop\node_modules\dsh-job-skill-plugin`。

### 7.3 卸载 sidecar

sidecar 不是服务，没有注册表项：关掉那个终端窗口即可；要连数据一起清就删 `starter\sidecar\.cache`（公司背调缓存）与 `reports`（导出的报告）。

---

## 8. 本次安装的自检记录

| 项 | 结果 |
|---|---|
| DSH 版本 | 0.2.1-rc.5 |
| 插件版本 | 1.0.1（v1.0.0 的命令形状有缺陷，已修） |
| 插件加载 | 成功（`load.log` 有 `plugin=…` 与 `cmdcheck name=job-fit registered=/feedback,/job-fit`） |
| Skill 注册 | 成功（DSH 会话里出现「加载技能 job-fit-orchestrator」，斜杠菜单「技能」分组可见） |
| 工具调用 | 成功（sidecar 收到 `/v1/resume/parse`、`/v1/jd/decode`、`/v1/company/recon`，均 200） |
| 编排接口 | 成功（sidecar 收到 `POST /v1/analysis` 200 与 `POST /v1/report/export` 200） |
| 命令 `/job-fit` | **已生效**（桌面端斜杠菜单可见、执行成功，证据 `docs/evidence/dsh-desktop-slash-menu-crop.png`） |
| 完整一轮 | 传简历 + 贴 JD + 报公司名 → 摘要卡片 + 报告文件卡片 + 四条核对（声明 1 次 / `evidence_ref` 8 处 = 8 道题 / Mock 14 处 / 与服务端原文哈希一致）→ 追问一轮（只读报告，未重跑生成器） |
| 验收脚本 | `bash scripts/verify.sh` 全绿：pytest 180 / 插件 30 / golden 7/7 |
