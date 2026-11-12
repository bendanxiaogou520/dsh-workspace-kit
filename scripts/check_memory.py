# -*- coding: utf-8 -*-
"""记忆自检：MEMORY.md / 最近.md / projects / 技术 的一致性与膨胀检查。

用法（在你自己工作空间的根目录下）：
    python memory/check_memory.py
    python memory/check_memory.py --fix     # 自动把超期日志搬进 归档/
    python memory/check_memory.py --quiet   # 只报问题

六个检查项
  [1] MEMORY.md 体积 —— 它每轮自动进上下文，超上限就是每轮多付钱
  [2] 条目长度 —— 超长的条目是"把细节写进了索引"，该搬去项目页
  [3] 索引条数 —— 顶部索引表声称的条数 vs 实际数出来的
  [4] 重复 —— 同一条事实写了两遍（MEMORY 内部，或 MEMORY 抄了项目页）
  [5] 漏更新 —— 项目页比 MEMORY.md 新（改了细节没回来看一眼索引）
  [6] 最近.md —— 超过 N 天的日志没归档

设计原则：**只读、只提示、不擅自改内容**。--fix 只做一件事：搬日志进归档。
"""
import io
import os
import re
import sys
import datetime
import shutil

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(BASE, "memory")
MEMORY_MD = os.path.join(MEM, "MEMORY.md")
RECENT_MD = os.path.join(MEM, "最近.md")
ARCHIVE_DIR = os.path.join(MEM, "归档")
PROJECTS_DIR = os.path.join(BASE, "projects")
TECH_DIR = os.path.join(MEM, "技术")

SECTIONS = ["档案", "偏好", "学业", "项目", "技术", "其他"]

# ---- 阈值（觉得吵就调这里）----
# ★★★ 2026-11-12 他追问：「所以为什么要限制字符呢」
#   诚实结论：**没有正当理由**。字符数只是「有没有抄重复」的代理指标，
#   用字数卡条目 = 用体重判断健康，只会逼人删掉真正有用的前提。
#   唯一真实的判据只有一句：**这条信息项目页里已经有了吗？有就一个不写，没有就写全。**
#   → 下面所有数字都降级成「报警线」：超过只提醒，永远不拦、不要求删。
#   ★ 实测（2026-11-12）：MEMORY.md 16454 字符 ≈ 9435 tokens；
#     而工具定义本身就有 170K tokens —— 容量从来不是瓶颈，我一直在为一个不存在的威胁守着规矩。
MAX_MEMORY_CHARS = 60000     # 报警线（原 12000→20000→60000）。超了只提示「看看是不是抄重复了」，不拦。
                             # 真要判重复，看下面 [4] 的 n-gram 重叠检测，那个才是有效信号。
ITEM_MAX = {                 # 单条「提醒线」（超了只提示，不是错误）
    "档案": 2000,
    "偏好": 2000,
    "学业": 2500,
    "项目": 1500,             # 原为 220，逼我把「为什么要开这个文件」的关键前提删掉。
                             #   项目条目不该抄项目页正文，但**钩子该有的信息量必须留**（触发词、关键前提、路径、别忘了的事）。
                             #   ⚠️ 判据不是字数，是「这条信息项目页里有没有」：有就一个都不写；没有就写全，别为了字数砍。
    "技术": 2000,
    "其他": 2000,
}
RECENT_KEEP_DAYS = 3         # 最近.md 保留几天
DUP_NGRAM = 12               # 重复检测的连续字符窗口
DUP_RATIO = 0.30             # 重叠率超过这个比例算"抄"

TODAY = datetime.date.today()


def read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def ngrams(s, n=DUP_NGRAM):
    """去空白与 markdown 符号后切连续 n 字窗口。中文按字切。"""
    t = re.sub(r"[\s`*>#>|\-]+", "", s)
    if len(t) < n:
        return set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def parse_memory(text):
    """返回 {分类: [(行号, 原文), ...]}"""
    out = {k: [] for k in SECTIONS}
    sec = None
    for i, ln in enumerate(text.split("\n"), 1):
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            sec = m.group(1) if m.group(1) in SECTIONS else None
            continue
        if sec and ln.startswith("- ") and not ln.startswith("- ★") and not ln.startswith("- ⚠"):
            out[sec].append((i, ln))
    return out


def parse_index(text):
    """从顶部索引表读出声称的条数。"""
    claimed = {}
    for ln in text.split("\n"):
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] in SECTIONS and cells[2].isdigit():
            claimed[cells[0]] = int(cells[2])
    return claimed


def short(text, n=46):
    t = re.sub(r"[`*]", "", text)
    t = re.sub(r"^-\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n] + ("…" if len(t) > n else "")


def load_refs():
    r"""把 projects\ + memory\技术\ 全部读成一个 [(相对路径, 全文)]，用于重复检测。"""
    refs = []
    for d in (PROJECTS_DIR, TECH_DIR):
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.endswith(".md"):
                    p = os.path.join(root, fn)
                    try:
                        refs.append((os.path.relpath(p, BASE), read(p)))
                    except OSError:
                        pass
    return refs


# ---------------- 检查 ----------------

def check_size(text):
    n = len(text)
    nlines = text.count("\n") + 1
    ok = n <= MAX_MEMORY_CHARS
    tail = "" if ok else "  ← 超了 %d 字符，该动手了" % (n - MAX_MEMORY_CHARS)
    line = "%s MEMORY.md  %d 字符 / %d 行  （上限 %d）%s" % (
        "✅" if ok else "⚠️", n, nlines, MAX_MEMORY_CHARS, tail)
    return "      " + line, ok


def check_items(items):
    rows = []
    ok = True
    for sec in SECTIONS:
        lst = items[sec]
        if not lst:
            rows.append("      %-4s  0 条" % sec)
            continue
        limit = ITEM_MAX[sec]
        lens = [(len(t), ln, t) for ln, t in lst]
        over = [x for x in lens if x[0] > limit]
        mx = max(lens)[0]
        mark = "✅" if not over else "⚠️"
        rows.append("      %s %-4s %2d 条  最长 %4d 字符  上限 %d" % (mark, sec, len(lst), mx, limit))
        if over:
            ok = False
            over.sort(reverse=True)
            for L, ln, t in over[:6]:
                rows.append("           行%-4d %4d 字符  %s" % (ln, L, short(t)))
            if len(over) > 6:
                rows.append("           …… 另 %d 条超长" % (len(over) - 6))
    return "\n".join(rows), ok


def check_index(text, items):
    claimed = parse_index(text)
    rows = []
    ok = True
    for sec in SECTIONS:
        if sec not in claimed:
            continue
        real = len(items[sec])
        if real != claimed[sec]:
            ok = False
            rows.append("      ⚠️ %-4s 索引写 %d，实际 %d" % (sec, claimed[sec], real))
        else:
            rows.append("      ✅ %-4s %d" % (sec, real))
    return "\n".join(rows), ok


def check_dup(items, refs):
    """两条路：①MEMORY 内部两两 ②每条 vs 项目页/技术页。"""
    rows = []
    ok = True
    flat = []
    for sec in SECTIONS:
        for ln, t in items[sec]:
            ng = ngrams(t)
            if ng:
                flat.append((sec, ln, t, ng))

    # ① 内部互抄
    hits = []
    for i in range(len(flat)):
        for j in range(i + 1, len(flat)):
            a, b = flat[i][3], flat[j][3]
            inter = a & b
            if not inter:
                continue
            r = len(inter) / float(min(len(a), len(b)))
            if r >= DUP_RATIO:
                hits.append((r, flat[i], flat[j]))
    if hits:
        ok = False
        hits.sort(reverse=True)
        rows.append("      ⚠️ MEMORY 内部重复 %d 对：" % len(hits))
        for r, A, B in hits[:5]:
            rows.append("           %.0f%%  %s 行%-4d ⟷ 行%-4d" % (r * 100, A[0], A[1], B[1]))
            rows.append("                  %s" % short(A[2]))
            rows.append("                  %s" % short(B[2]))
    else:
        rows.append("      ✅ MEMORY 内部没有互相抄的条目")

    # ② 抄了项目页 / 技术页
    ref_ng = []
    for rel, body in refs:
        ng = ngrams(body)
        if ng:
            ref_ng.append((rel, ng))
    copied = []
    for sec, ln, t, ng in flat:
        for rel, rng in ref_ng:
            inter = ng & rng
            if not inter:
                continue
            r = len(inter) / float(len(ng))
            if r >= DUP_RATIO:
                copied.append((r, sec, ln, t, rel))
                break
    if copied:
        ok = False
        copied.sort(reverse=True)
        rows.append("      ⚠️ 有 %d 条索引内容几乎能在别的文件里找到（该改成一行动作/指路）：" % len(copied))
        for r, sec, ln, t, rel in copied[:8]:
            rows.append("           %.0f%%  %s 行%-4d → %s" % (r * 100, sec, ln, rel))
            rows.append("                  %s" % short(t))
    else:
        rows.append("      ✅ 索引里没有大段照抄项目页的内容")
    return "\n".join(rows), ok


def check_stale(memory_mtime):
    if not os.path.isdir(PROJECTS_DIR):
        return "      （没有 projects\\ 目录）", True
    newer = []
    for fn in sorted(os.listdir(PROJECTS_DIR)):
        if not fn.endswith(".md") or fn == "INDEX.md":
            continue
        p = os.path.join(PROJECTS_DIR, fn)
        mt = os.path.getmtime(p)
        if mt > memory_mtime + 60:
            newer.append((mt, fn))
    if not newer:
        return "      ✅ 没有项目页比 MEMORY.md 新", True
    newer.sort(reverse=True)
    rows = ["      ⚠️ %d 个项目页比 MEMORY.md 新 —— 顺手看一眼索引那行还准不准：" % len(newer)]
    for mt, fn in newer[:8]:
        rows.append("           %s  %s" % (
            datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M"), fn))
    return "\n".join(rows), False


def parse_recent(text):
    """返回 [(date, 段全文, 段起行号)]"""
    lines = text.split("\n")
    out = []
    cur = None
    buf = []
    start = 0
    for i, ln in enumerate(lines, 1):
        m = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", ln)
        if m:
            if cur is not None:
                out.append((cur, "\n".join(buf), start))
            try:
                cur = datetime.date(*map(int, m.group(1).split("-")))
            except ValueError:
                cur = None
            start = i
            buf = [ln]
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        out.append((cur, "\n".join(buf), start))
    return out


def check_recent(do_fix):
    if not os.path.exists(RECENT_MD):
        return "      ⚠️ 没有 memory\\最近.md（AGENTS.md 第 3 条要读它）", False
    text = read(RECENT_MD)
    segs = parse_recent(text)
    if not segs:
        return "      ⚠️ 最近.md 里没有任何 `## YYYY-MM-DD` 段落", False

    days = sorted({d for d, _s, _i in segs}, reverse=True)
    old = [d for d in days if (TODAY - d).days > RECENT_KEEP_DAYS]
    head = "      %s 共 %d 天：%s ～ %s" % (
        "✅" if not old else "⚠️", len(days), days[-1].isoformat(), days[0].isoformat())
    if not old:
        return head + "（都在 %d 天内）" % RECENT_KEEP_DAYS, True

    detail = "，需归档 %d 天（%s）" % (len(old), "、".join(d.isoformat() for d in old))
    if not do_fix:
        return head + detail + "\n           跑 `--fix` 自动搬进 `memory\\归档\\YYYY-MM.md`", False

    # ---- 真搬 ----
    shutil.copy2(RECENT_MD, RECENT_MD + ".bak")
    by_month = {}
    for d, seg, _i in segs:
        if d in old:
            by_month.setdefault(d.strftime("%Y-%m"), []).append((d, seg))
    if not os.path.isdir(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)

    moved_chars = 0
    for month, lst in by_month.items():
        ap = os.path.join(ARCHIVE_DIR, month + ".md")
        if os.path.exists(ap):
            body = read(ap)
            if not body.endswith("\n"):
                body += "\n"
            body += "\n"
        else:
            body = u"# 记忆归档 · %s\n\n> 从 `memory\\最近.md` 自动搬来。按天保留原样，供查「上次那次怎么弄的」。\n\n" % month
        for d, seg in lst:
            body += seg.rstrip("\n") + "\n\n"
            moved_chars += len(seg)
        with io.open(ap, "w", encoding="utf-8", newline="\n") as f:
            f.write(body.rstrip("\n") + "\n")

    # 重建 最近.md：保留第一个日期段之前的所有内容，再拼剩下的段
    lines = text.split("\n")
    first_seg_line = min(i for _d, _s, i in segs)
    header = "\n".join(lines[:first_seg_line - 1]).rstrip("\n")
    keep = [seg for d, seg, _i in segs if d not in old]
    new_text = header + "\n\n" + ("\n\n".join(s.rstrip("\n") for s in keep) if keep else "") + "\n"
    with io.open(RECENT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)

    return head + detail + "\n           ✅ 已搬 %d 天进归档（%d 字符），原文件备份为 `最近.md.bak`" % (
        len(old), moved_chars), True


def main():
    do_fix = "--fix" in sys.argv
    quiet = "--quiet" in sys.argv

    if not os.path.exists(MEMORY_MD):
        print("找不到 %s" % MEMORY_MD)
        return 2

    text = read(MEMORY_MD)
    items = parse_memory(text)
    refs = load_refs()

    print("=" * 70)
    print("记忆自检  |  %s  |  工作区 %s" % (TODAY.isoformat(), BASE))
    print("=" * 70)

    bad = 0
    line, ok = check_size(text)
    print("\n[1] 体积")
    print(line)
    bad += 0 if ok else 1

    print("\n[2] 条目长度")
    block, ok = check_items(items)
    print(block)
    bad += 0 if ok else 1

    print("\n[3] 索引条数")
    block, ok = check_index(text, items)
    print(block)
    bad += 0 if ok else 1

    print("\n[4] 重复检测（窗口 %d 字，重叠 ≥%.0f%% 算抄）" % (DUP_NGRAM, DUP_RATIO * 100))
    block, ok = check_dup(items, refs)
    print(block)
    bad += 0 if ok else 1

    print("\n[5] 漏更新")
    block, ok = check_stale(os.path.getmtime(MEMORY_MD))
    print(block)
    bad += 0 if ok else 1

    print("\n[6] 最近.md（保留 %d 天）" % RECENT_KEEP_DAYS)
    block, ok = check_recent(do_fix)
    print(block)
    bad += 0 if ok else 1

    print("\n" + "=" * 70)
    if bad == 0:
        print("全绿。记忆库是干净的。")
    else:
        print("%d 项要处理。" % bad)
        print("处理顺序建议：先看 [2] 超长条目（把细节搬去项目页）→ 再改 [3] 索引条数 → "
              "最后看 [4]/[5] 是不是真的。")
    print("=" * 70)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
