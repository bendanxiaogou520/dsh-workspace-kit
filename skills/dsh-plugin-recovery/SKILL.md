---
name: dsh-plugin-recovery
description: "DSH 插件突然从设置里消失（或更新后一次少几个）的恢复流程：根因是市场为保启动而删掉 dependencies 与 bundles 双声明、从 .dsh-market/log.ndjson 账本找回清单、用现有工具一键恢复、验证与预防，以及和凭据丢失/启动崩溃的分诊。当插件更新失败、插件不见、或 package.json 里的声明消失时使用。"
---

# DSH 插件凭空消失的恢复

适用：DSH 里装的插件**突然从设置里不见了**，或者更新插件后一次少了几个。
典型触发：「插件没了」「插件更新后消失」「市场更新失败」「profile 里的包不见了」
「明明装过但设置里没有」。

**结论先说：这是市场在自保，不是你操作错了。有现成工具能全部恢复。**

---

## 0. 症状识别

- 设置 → 插件 里某个（或几个）插件**不在了**，但你确定装过、也在用。
- 通常发生在**点过「更新」之后**，可能一次消失 2～4 个。
- `~\.dsh\profiles\<profile>\package.json` 里那个包**同时从两处消失**：
  - `dependencies`
  - `dsh.profile.bundles`

★ **先确认 profile**：他跑的是**桌面端**（`deepseek harness.exe`）→
`~\.dsh\profiles\desktop\`。**改 `web` profile 对他不生效**
（这个搞错过一整轮）。

---

## 1. 根因（知道原因才不会乱修）

```
市场更新插件 → pnpm 换不了 DSH 正在占用的文件 → 更新失败
→ 旧版本变成 incomplete
→ 市场为了「下次还能启动」，把这个包从 dependencies 和 bundles 里
   一起删掉 → 插件静默消失
```

**这是设计，不是 bug。** 市场宁可少一个插件也要保证能开机。

⚠️ 所以 **DSH 开着时更新插件 = 高风险**，一次可能带走好几个。

---

## 2. 恢复：读市场自己的账本，别靠记忆

市场的日志在 `~\.dsh\.dsh-market\log.ndjson`（JSON Lines），
里面 `update-removed-declaration` 条目**记录了它历史上删过的每一个包**。

```bash
# 先看它删过谁（这一步是只读的，安全）
grep -o '"update-removed-declaration"[^}]*' ~/.dsh/.dsh-market/log.ndjson | tail -20
```

★ **这是最好的数据源** —— 比硬编码清单、比记忆都准，能覆盖「这一次」删掉的。

---

## 3. 用现成工具跑

```bash
cd "<工作区>"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\restore-dropped-plugins.bat"
```

工具会做四件事：
1. 读 `.dsh-market\log.ndjson` 找出所有被删过的包
2. **备份**当前 `package.json` 到 `_restore-backup\`
3. 把包**重新写回** `dependencies` + `dsh.profile.bundles`
4. 跑 `update-plugins.cjs` 安装

**退出码**：`0` 完成 / `1` 失败 / `2` 环境不对 / `3` 没有需要恢复的。

★ **必须在 DSH 关闭时跑**（安装没法替换被占用的文件）。
脚本**不会自己杀 DSH**，要你手动关。

### ★ 一个已知的小毛病
批量装多个包时，可能有个别报 `STILL MISSING` —— **单独再跑一次就成**
（实测 `@michengai/dsh-btw` 就是这样）。

---

## 4. 验证是否真的回来了

```bash
# 数量对不上就是没全回来
powershell.exe -NoProfile -Command "
\$p = Join-Path \$env:USERPROFILE '.dsh\profiles\desktop\package.json'
\$j = Get-Content \$p -Raw | ConvertFrom-Json
Write-Output ('dependencies: ' + (\$j.dependencies.PSObject.Properties.Name).Count)
Write-Output ('bundles: ' + \$j.dsh.profile.bundles.Count)
"
```

然后**重启 DSH**，去设置里看插件是否回来。

配套还有个 `tools\verify-plugins.cjs` 可以做结构校验。

---

## 5. 预防

- **更新插件前先关 DSH**。这条能挡住绝大多数事故。
- 更新完**立刻扫一眼插件列表数量**，少了就马上跑恢复（趁日志还新）。
- `package.json` 已经被 `restore-dropped-plugins.bat` 自动备份到
  `_restore-backup\`，真搞砸了从那里回滚。

---

## 6. 如果工具也救不回来

1. **看 `.dsh-market\log.ndjson` 里到底删了什么**（可能是你没装的包名）。
2. **手动补两处声明**（缺一不可）：
   ```json
   {
     "dependencies": { "@scope/pkg": "^1.2.3" },
     "dsh": { "profile": { "bundles": ["@scope/pkg"] } }
   }
   ```
   ★ **只写 `dependencies` 不够**，`bundles` 里不加，插件不会被加载。
3. 再 `pnpm install`（在 profile 目录里）。
4. **别改 `.credentials.yaml` 顺手「修一下」** —— 改配置会把它整份重写成
   当前登记过的 provider，**没登记的 API key 会直接丢**（DSH 凭据丢失事故就是这么来的）。
   如果机器人开始回「脑子卡住了」，先看 `qq\logs\bridge.log` 里的 `MISSING_CREDENTIAL`。

---

## 7. 相邻问题的分诊

| 症状 | 是不是这个技能管的 | 去看哪 |
| --- | --- | --- |
| 插件从设置里消失 | ✅ 是 | 本技能 |
| 插件装了但工具调用不出来 | ❌ 不是 | `memory\技术\DSH与模型.md`（MCP 要 streamable-http，stdio 必挂） |
| 设置显示已登录但报没 key | ❌ 不是 | 凭据问题，见第 6 节第 4 条 |
| 启动就崩 / 打不开 | ❌ 不是 | `projects\DSH启动稳定性.md` |
