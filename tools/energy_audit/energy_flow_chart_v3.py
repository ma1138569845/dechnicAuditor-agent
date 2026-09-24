#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图5.1 能源流向图 v3 —— 横式层级黑白（仿标准化参考样图；2026-09-24 移植自参照包）。

样式规范（与参照包 `make_flow_figs_v3.py` / `references/energy-flow-diagrams.md` 一致）：
  · 横向分层：最左=能源品种，向右逐级流向；同层一列，列内竖向均匀（叶子等距槽位，父=子叶中点）
  · 节点：白底、黑色直角细框（lw≈0.9）、单行居中、无圆角；框高≈0.34in；**同层等宽**
  · 连线：正交主线走线（父右缘中点 → 列间正中竖主线 → 各子水平引入，黑箭头 -|> 指向子框左缘）
  · 字号按层级递减：L1 14pt / L2 12pt / L3 10pt（跨批一致）
  · 字体：**宋体 SimSun**（公文同源、Windows 自带，避开参照包 .ttc 多 face 坑）
  · 配色：纯黑白灰（用户明确"不用彩色"）
  · 输出：dpi=300、bbox_inches='tight'、pad=0.10；**图内不画标题**（标题由 Word 图注承担，
    避免与"图5.1 能源流向图"重复）

与参照包的**差异**（本项目决策，2026-09-24）：
  · 一张**综合图**（多棵能源树合成，虚拟根不画框），不是 5 张分能源图；
  · 默认画**全深度**（能源品种 → 用途分类 → 用能系统 → 终端设备），与房式样图
    （省高院历史报告 p13 的"能源流向图"）逐列一致；设备明细**在图上**保留，
    因为现场实际设备是这张图最有价值的信息（旧实现曾在这里写死默认设备名）。
    如需裁剪层数，显式传 `max_depth=N`（硬上限 5 层，防病态深树）。
  · 无客户树时由调用方退化为"能源品种 → 用能系统"两层（本文件只负责画，不做取数）。

取数与调用：
    from tools.energy_audit.energy_flow_chart_v3 import draw_energy_flow_forest
    draw_energy_flow_forest(trees, unit_name='XX单位', out_path='chart_dir/energy_flow.png')

`trees` 形如 `[{'name': '电能', 'children': [{'name': '空调用电', 'children': [...]}, ...]}, ...]`,
由 `ts_energy_flow(_level)` 的客户树转换而来（见 pg_query.get_energy_flow_trees）。
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

# ---------- 样式常量（对齐参照包） ----------
FS = {1: 14.0, 2: 12.0, 3: 10.0, 4: 9.0, 5: 8.5}
BOX_H = 0.34          # 节点框高（英寸）
PAD = 0.11            # 框内文字左右留白（英寸）
GAPX = 0.52           # 列间距（英寸）
LEAF_GAP = 0.15       # 相邻叶子垂直间距（英寸）
MARGIN = 0.14         # 画布左右留白（英寸）
EDGE_C = "#111111"    # 连线/边框颜色
L_W = 0.9

# 字体：宋体（Windows 自带）；可用环境变量覆盖
FONT_CANDIDATES = (
    os.environ.get("EA_FLOW_FONT", ""),
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simsun.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
)

_FONT_PROP = None


def _font_prop():
    """惰性注册宋体，返回 FontProperties（找不到则用 matplotlib 默认字体，仍可出图）。"""
    global _FONT_PROP
    if _FONT_PROP is not None:
        return _FONT_PROP
    for cand in FONT_CANDIDATES:
        if cand and os.path.isfile(cand):
            try:
                font_manager.fontManager.addfont(cand)
                _FONT_PROP = font_manager.FontProperties(fname=cand)
                plt.rcParams["axes.unicode_minus"] = False
                return _FONT_PROP
            except Exception:  # noqa: BLE001
                continue
    _FONT_PROP = font_manager.FontProperties()
    return _FONT_PROP


def _box_w(name: str, level: int) -> float:
    """按字号估框宽：中文全角≈1em（pt→英寸）。"""
    fs = FS.get(level, 9.0)
    return len(name) * (fs / 72.0) + PAD * 2


MAX_DEPTH = 5          # 硬上限（FS 字号表最深层级）


def _trim(tree: Dict, max_depth: Optional[int], lv: int = 1) -> Dict:
    """按 max_depth 裁层；max_depth 为 None 时保留全深度（只受 MAX_DEPTH 兜底）。"""
    kids = list(tree.get("children") or [])
    if max_depth is not None and lv >= max_depth:
        kids = []
    return {
        "name": tree.get("name", ""),
        "children": [_trim(c, max_depth, lv + 1) for c in kids],
    }


def draw_energy_flow_forest(
    trees: List[Dict],
    unit_name: str = "",
    out_path: str = "energy_flow.png",
    max_depth: Optional[int] = None,
    dpi: int = 300,
) -> str:
    """多棵能源树合成**一张**横式层级黑白流向图；返回 PNG 路径（无树时返回 ''）。

    unit_name 仅用于日志/元信息——图内**不画标题**（标题交给 Word 图注）。
    max_depth=None（默认）画全深度，最多 MAX_DEPTH 层。
    """
    trees = [t for t in (trees or []) if t and t.get("name")]
    if not trees:
        return ""
    cap = min(int(max_depth), MAX_DEPTH) if max_depth else MAX_DEPTH
    roots = [_trim(t, cap) for t in trees]

    # ---- 层级与列宽 ----
    level_nodes: Dict[int, list] = {}
    level_w: Dict[int, float] = {}
    lv_of: Dict[int, int] = {}

    def walk(n, lv):
        lv_of[id(n)] = lv
        level_nodes.setdefault(lv, []).append(n)
        level_w[lv] = max(level_w.get(lv, 0.0), _box_w(n["name"], lv))
        for c in n["children"]:
            walk(c, lv + 1)

    for r in roots:                     # 多棵树：第 1 层并列
        walk(r, 1)
    maxd = max(level_nodes) if level_nodes else 1

    xs: Dict[int, float] = {}
    xcur = MARGIN
    for lv in range(1, maxd + 1):
        xs[lv] = xcur + level_w[lv] / 2.0
        xcur += level_w[lv] + GAPX
    W = xcur - GAPX + MARGIN

    # ---- y：叶子按 DFS 等距槽位；父=子叶槽中点 ----
    leaf_idx: Dict[int, int] = {}
    leaves: list = []

    def dfs(n):
        if not n["children"]:
            leaf_idx[id(n)] = len(leaves)
            leaves.append(n)
            return
        for c in n["children"]:
            dfs(c)

    for r in roots:
        dfs(r)
    N = len(leaves)
    S = BOX_H + LEAF_GAP
    ypos: Dict[int, float] = {}

    def assign(n):
        d, stack = [], [n]
        while stack:
            x = stack.pop()
            if not x["children"]:
                d.append(leaf_idx[id(x)])
            else:
                stack.extend(x["children"])
        # y 轴反转：第 1 棵树占最上一条槽位，阅读顺序自上而下 = trees 顺序
        ypos[id(n)] = (N - 1 - (min(d) + max(d)) / 2.0) * S
        for c in n["children"]:
            assign(c)

    for r in roots:
        assign(r)
    H = (N - 1) * S + BOX_H

    fig = plt.figure(figsize=(W + 1.2, H + 1.2), dpi=dpi)
    ax = fig.add_subplot(111)
    ax.axis("off")
    fp = _font_prop()

    def connect(pa):
        chs = pa["children"]
        if not chs:
            return
        lv_p = lv_of[id(pa)]
        x0 = xs[lv_p] + level_w[lv_p] / 2.0
        y0 = ypos[id(pa)]
        x1 = xs[lv_p + 1] - level_w[lv_p + 1] / 2.0
        y1s = [ypos[id(c)] for c in chs]
        if len(chs) == 1 and abs(y0 - y1s[0]) < 1e-9:      # 单链：直接水平箭头
            ax.annotate("", xy=(x1, y1s[0]), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="-|>", color=EDGE_C, lw=L_W,
                                        mutation_scale=11, shrinkA=0, shrinkB=0),
                        zorder=2)
            return
        xm = x0 + (x1 - x0) * 0.5                          # 列间正中竖主线
        lo, hi = min([y0] + y1s), max([y0] + y1s)
        ax.plot([xm, xm], [lo, hi], color=EDGE_C, lw=L_W, zorder=2)
        ax.plot([x0, xm], [y0, y0], color=EDGE_C, lw=L_W, zorder=2)
        for y1 in y1s:
            ax.annotate("", xy=(x1, y1), xytext=(xm, y1),
                        arrowprops=dict(arrowstyle="-|>", color=EDGE_C, lw=L_W,
                                        mutation_scale=11, shrinkA=0, shrinkB=0),
                        zorder=2)

    def edges(n):
        connect(n)
        for c in n["children"]:
            edges(c)

    for r in roots:
        edges(r)

    def node(n, lv):
        x, y = xs[lv], ypos[id(n)]
        w, fs = level_w[lv], FS.get(lv, 9.0)
        ax.add_patch(Rectangle((x - w / 2.0, y - BOX_H / 2.0), w, BOX_H,
                               facecolor="white", edgecolor=EDGE_C, lw=L_W, zorder=3))
        ax.text(x, y, n["name"], ha="center", va="center", fontsize=fs,
                color="#000000", zorder=4, fontproperties=fp)
        for c in n["children"]:
            node(c, lv + 1)

    for r in roots:
        node(r, 1)

    # 单链/窄图必须显式限定范围（参照包实测：autoscale 对零范围数据失效 → 图被拉成宽条）
    ax.set_xlim(0.0, W + MARGIN)
    ax.set_ylim(-0.4, H + 0.4)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor="white",
                bbox_inches="tight", pad_inches=0.10)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    print(__doc__)
