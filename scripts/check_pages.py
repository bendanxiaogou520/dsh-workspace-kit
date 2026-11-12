"""项目页体检 + 速览生成

用法：
    .\\pyenv\\Scripts\\python.exe projects\\check_pages.py          # 只检查
    .\\pyenv\\Scripts\\python.exe projects\\check_pages.py --fix    # 顺便刷新速览块

只做两件事：
  1. 在每个项目页顶部维护一个「速览」块（当前状态 / 待办 / 最近进度 / 章节导航）
  2. 报告超长、待办积压、速览过期

--fix 绝不删正文、不改正文，只重写两个标记之间的那段。
"""

import os
import re
import sys
import glob
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(ROOT, "projects")

MARK_START = "<!-- AUTO-SUMMARY:START -->"
MARK_END = "<!-- AUTO-SUMMARY:END -->"

# 体积是「提示」不是「错误」：项目页里有大量知识型长节（踩过的坑、成果、操作手册），
# 长是正常的，砍了才是损失。真正要治的是「接手时读不进去」，而那个由顶部速览 + 章节导航解决。
PAGE_HINT_CHARS = 15000
TODO_DONE_WARN = 10          # 待办节里 [x] 超过这么多，才是真问题（该搬走）
RECENT_PROGRESS = 5          # 速览里带几条最近进度


def clip(s, n):
    """截断到 n 字符以内，尽量断在句读处，并加省略号"""
    if len(s) <= n:
        return s
    seg = s[:n]
    for cut in ("。", "；", "，", " "):
        i = seg.rfind(cut)
        if i >= n * 0.6:
            return seg[: i + 1] + "…"
    return seg + "…"


def char_count(s):
    return len(s)


def split_sections(text):
    """返回 [(标题, 起始行号(0-based), 行列表)]，第一项标题为 None 表示文件头"""
    out = []
    title, start, buf = None, 0, []
    for i, line in enumerate(text.splitlines()):
        if line.startswith("## "):
            out.append((title, start, buf))
            title, start, buf = line[3:].strip(), i, []
        else:
            buf.append(line)
    out.append((title, start, buf))
    return out


def strip_auto_block(text):
    """去掉已有的速览块，返回 (纯正文, 是否有旧的速览块)"""
    m = re.search(re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\n?", text, re.S)
    if not m:
        return text, False
    return text[: m.start()] + text[m.end():], True


def parse_page(path):
    raw = open(path, encoding="utf-8").read()
    body, had = strip_auto_block(raw)
    secs = split_sections(body)
    head_lines = secs[0][2]
    total = char_count(body)
    all_lines = body.splitlines()

    # 状态行
    status = ""
    for line in head_lines:
        if line.startswith("状态："):
            status = line.strip()
            break

    # 未完成待办
    todos = []
    for title, _, lines in secs[1:]:
        if title and "待办" in title:
            for line in lines:
                st = line.strip()
                if st.startswith("- [ ]") or st.startswith("* [ ]"):
                    todos.append(st[5:].strip())

    # 最近进度（去掉行首列表符号，速览里统一加）
    recent = []
    done_in_todo = 0
    for title, _, lines in secs[1:]:
        if title and "待办" in title:
            done_in_todo += sum(
                1 for line in lines if line.strip().startswith(("- [x]", "* [x]"))
            )
        if title and title.startswith("进度"):
            for line in lines:
                st = line.strip()
                if st.startswith(("- **", "* **", "- 2026-", "* 2026-")):
                    st = re.sub(r"^[-*]\s+", "", st)
                    recent.append(st)
    recent = recent[-RECENT_PROGRESS:]

    # 章节导航
    nav = []
    for title, start, lines in secs[1:]:
        n = char_count("\n".join(lines))
        nav.append((title, start + 1, n))   # 1-based 行号

    return {
        "raw": raw,
        "body": body,
        "had_auto": had,
        "status": status,
        "todos": todos,
        "recent": recent,
        "nav": nav,
        "total": total,
        "done_in_todo": done_in_todo,
        "head_end": len(secs[0][2]),
        "n_sections": len(secs) - 1,
    }


def render_summary(info, today, nav_real=None):
    out = [MARK_START]
    out.append(f"<!-- 由 projects\\check_pages.py 自动生成，勿手改。{today} -->")
    out.append("")
    out.append("### 速览（接手先看这 30 行，细节按下方导航跳读）")
    out.append("")
    if info["status"]:
        st = info["status"]
        st = re.sub(r"\s*\|\s*完成：\s*$", "", st)
        out.append(f"**{st}**")
        out.append("")
    out.append(f"- 规模：{info['total']} 字 / {info['n_sections']} 节")
    if info["todos"]:
        out.append(f"- **未完成待办（{len(info['todos'])} 条）**：")
        for t in info["todos"][:8]:
            out.append(f"  - {clip(t, 120)}")
        if len(info["todos"]) > 8:
            out.append(f"  - …… 还有 {len(info['todos']) - 8} 条，见页面「待办」节")
    else:
        out.append("- **未完成待办**：无")
    if info["recent"]:
        out.append("- 最近进度（倒序，只给开头，细节看 L 行号跳读）：")
        for r in info["recent"]:
            out.append(f"  - {clip(r, 100)}")
    if info["nav"]:
        out.append("")
        out.append("**章节导航**（`read <本文件> offset=<行号> limit=80`）")
        out.append("")
        for title, line, n in info["nav"]:
            if nav_real and title in nav_real:
                line = nav_real[title]
            flag = " ⚠️大" if n > 6000 else ""
            out.append(f"- `L{line}` **{title}**（{n} 字）{flag}")
    out.append("")
    out.append(MARK_END)
    return "\n".join(out)


def build_page(info, today):
    """把速览块插到文件头之后、第一个 ## 之前；导航行号按最终文件实际行号算"""
    lines = info["body"].splitlines(keepends=True)
    idx = info["head_end"]
    while idx < len(lines) and not lines[idx].startswith("## "):
        idx += 1
    head = "".join(lines[:idx]).rstrip("\n")
    rest = "".join(lines[idx:])

    # 第一遍：导航行号先按原值占位，只为数出块的行数
    draft = head + "\n\n" + render_summary(info, today) + "\n\n" + rest
    real = {}
    for i, l in enumerate(draft.splitlines(), 1):
        if l.startswith("## ") and l[3:].strip() not in real:
            real[l[3:].strip()] = i
    # 第二遍：用真实行号
    return head + "\n\n" + render_summary(info, today, nav_real=real) + "\n\n" + rest


def main():
    fix = "--fix" in sys.argv
    today = datetime.date.today().isoformat()

    files = [p for p in sorted(glob.glob(os.path.join(PAGES, "*.md")))]
    files = [p for p in files if os.path.basename(p) != "INDEX.md"]

    problems = 0
    print("=" * 70)
    print(f"项目页体检  |  {today}  |  {PAGES}")
    print("=" * 70)

    for p in files:
        name = os.path.basename(p)
        info = parse_page(p)
        n = info["total"]
        news = []
        hints = []

        if n > PAGE_HINT_CHARS:
            hints.append(f"体积 {n} 字（超 {PAGE_HINT_CHARS}）。先看章节导航，大节单独读")
        if info["done_in_todo"] > TODO_DONE_WARN:
            news.append(f"待办节里有 {info['done_in_todo']} 条 [x] 已完成，该搬去 _历史\\")
        if not info["had_auto"]:
            news.append("没有速览块，跑 --fix 生成")

        print(f"\n{name}  {n} 字 / {info['n_sections']} 节  待办 {len(info['todos'])} 条")
        for x in news:
            print(f"    ⚠️ {x}")
        for x in hints:
            print(f"    💡 {x}")
        if news:
            problems += 1

        if fix:
            new_text = build_page(info, today)
            if new_text != info["raw"]:
                # 先记下原 mtime：速览是自动派生的，刷新它不算「正文有新进展」，
                # 不能让 memory\check_memory.py 的 [5] 漏更新检查误报。
                old_stat = os.stat(p)
                open(p, "w", encoding="utf-8", newline="").write(new_text)
                os.utime(p, (old_stat.st_atime, old_stat.st_mtime))
                print("    ✅ 速览已刷新（mtime 已保持，不惊动体检脚本）")

    print("\n" + "=" * 70)
    if fix:
        print("已刷新全部速览块。")
    if problems:
        print(f"有 {problems} 个页面需要留意（上面打了 ⚠️）。")
        return 1
    print("全部干净。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
