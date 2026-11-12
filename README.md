<div align="center">

# DSH Workspace Kit

**Scripts and skills that keep an AI assistant's workspace from forgetting.**
**让 AI 助手记住你、管好文档、并且真的把备份推上去。**

[中文](#中文) · [English](#english)

</div>

---

## 中文

### 这是什么

一套跑在 AI 编程助手工作空间里的运维脚本 + 技能。

AI 助手最大的毛病是**会忘**：上下文一压缩、会话一换，昨天定下的规则、上周踩过的坑全没了。这套东西处理"记忆"这件事的三个具体故障：

| 故障 | 表现 | 脚本 |
| --- | --- | --- |
| 记忆膨胀 | 索引文件越写越长，每轮都塞进上下文，同一条事实还写了两遍 | `check_memory.py` |
| 项目页失忆 | 接手旧项目要从头顺读几千字，不知道看到哪了 | `check_pages.py` |
| 备份假象 | 本地天天 commit，远端一周没动，脚本还告诉你「已同步」 | `sync-to-github.ps1` |

### 三个脚本

**`check_memory.py`** — 六项体检：体积、单条长度、索引条数、重复、漏更新、日志超期。
只读只提示，`--fix` 只做一件事：把超期日志搬进归档。

**`check_pages.py`** — 给每个项目页顶部自动生成「速览块」：状态、规模、未完成待办、最近 5 条进度、**带真实行号的章节导航**。
接手时先读那 30 行，再按导航跳读，不用顺读几千字。

**`sync-to-github.ps1`** — 自动 commit + 推送，带系统代理自动探测、15 秒超时快速失败、推完再向远端确认一次。

> ### 这个脚本里有个真实的坑
>
> 早期版本用 `git log @{u}..HEAD` 判断「有没有东西要推」。如果分支**没有设置上游跟踪**，这条命令直接报错、错误又被 `2>$null` 吞掉 —— 结果永远显示「already in sync」。
>
> 作者的文档备份因此**整整七天没推上去**，本地 commit 攒了 61 个，而每次运行都告诉他「已同步，无需推送」。
>
> 现在的版本会显式检查上游：没有就自动 `--set-upstream-to`，实在不行就明确报错让你 `git push -u`。
>
> **教训：任何「什么都没发生」的判断，都要先确认判断本身没失败。**

### 两个技能

`skills/` 下是两份可直接喂给 AI 助手的 `SKILL.md`：

- **`dsh-plugin-recovery`** — DSH 插件突然从设置里消失怎么救：根因是插件市场为保启动删掉了双声明，从 `.dsh-market/log.ndjson` 账本找回清单，一键恢复，再验证。
- **`android-webview-app`** — 把一个 HTML 单页做成安卓 APK 的完整流程：Gradle 构建、签名发版、`file://` 路由坑、长按去浏览器感、自适应图标、热更新。

### 用法

```bash
# 放进你的工作空间
cp scripts/* <workspace>/tools/
cp -r skills/* ~/.dsh/skills/

python tools/check_memory.py
python tools/check_pages.py --fix
powershell -File tools/sync-to-github.ps1
```

脚本默认假设这样的目录结构（可以改）：

```
<workspace>/
  memory/MEMORY.md     # 索引，每轮进上下文
  memory/最近.md        # 最近 3 天日志
  memory/技术/*.md      # 专题
  projects/*.md        # 一条项目线一页
  .git/
```

### 适配说明

- `check_pages.py` 完全自适应：根目录从脚本自身位置推出来，拷到哪都能跑。
- `check_memory.py` 认的是 MEMORY.md 里的固定小节标题，改几行正则就能用在别的格式上。
- `sync-to-github.ps1` 只依赖 git 和一个配好的 origin，分支名自动读取。

<sub>从一个真实用了 40 多天的 AI 工作空间里长出来的，不是设计出来的。</sub>

---

## English

### What this is

Ops scripts and skills for an AI assistant's long-term workspace.

The hard problem isn't writing code — it's **memory**. Compress the context or start a new session, and yesterday's rules and last week's mistakes are gone. These three scripts target the three ways that breaks:

| Failure | What it looks like | Script |
| --- | --- | --- |
| Memory bloat | The index file grows every day, loads on every turn, and duplicates itself | `check_memory.py` |
| Project amnesia | Picking up an old project means scrolling thousands of words to find where you were | `check_pages.py` |
| Fake backups | Commits every day, remote untouched for a week, and the script says "already in sync" | `sync-to-github.ps1` |

### The scripts

**`check_memory.py`** — six checks: size, per-entry length, index counts, duplication, staleness, log age. Read-only by default; `--fix` only archives old logs.

**`check_pages.py`** — writes a "summary block" at the top of every project page: status, size, open TODOs, last five progress notes, and a section index **with real line numbers**. Read 30 lines instead of 5,000.

**`sync-to-github.ps1`** — commits and pushes with automatic proxy detection, a 15-second fast fail instead of a multi-minute hang, and a post-push remote confirmation.

> ### The bug worth reading
>
> The early version decided "is there anything to push?" with `git log @{u}..HEAD`. With **no upstream branch configured**, that command errors out and the error was swallowed by `2>$null` — so it always reported "already in sync".
>
> The author's documentation backup sat **seven days / 61 commits** behind, while every run cheerfully said there was nothing to push.
>
> Now it checks the upstream explicitly and sets it when missing.
> **Lesson: any "nothing happened" verdict has to confirm that the check itself didn't fail.**

### The skills

- **`dsh-plugin-recovery`** — recovering DSH plugins that vanish from settings after a failed market update.
- **`android-webview-app`** — turning a single HTML page into a signed Android APK, including the `file://` routing traps.

### Usage

```bash
cp scripts/* <workspace>/tools/
cp -r skills/* ~/.dsh/skills/

python tools/check_memory.py
python tools/check_pages.py --fix
powershell -File tools/sync-to-github.ps1
```

MIT licensed. Issues and PRs welcome.

<sub>Grown out of 40+ days of real use, not designed in advance.</sub>
