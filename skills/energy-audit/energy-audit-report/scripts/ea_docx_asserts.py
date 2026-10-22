#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ea_docx_asserts.py — 能源审计报告 .docx/.pdf 交付断言器（脚本化装配方案 T0）。

用法:
    python ea_docx_asserts.py <报告.docx> [--pdf <报告.pdf>] [--expect k=v ...] [--json out.json]

硬检查（任一失败 → exit 1）:
    zip_ok            docx 可解包
    toc_field         document.xml 含 TOC 域（instrText 含 'TOC'）
    update_fields     word/settings.xml 含 <w:updateFields>
    header_watermark  前置/正文两节页眉均含 EAWatermark（DrawingML 水印）
    header_divider    正文节页眉含 w:pBdr 底边线；前置节页眉不得含边框
    footer_page       正文节页脚含 PAGE 域
    footer_plain      正文节页脚为纯数字（无「—」或其它文字）
    header_no_vml     页眉无 VML 水印（禁 v:textpath）
    section_split     节数=2（前置节/正文节；2026-09-22 分节）
    prebody_clean     前置节：无页脚引用、页眉无文字、无边框（仅水印）
    cover_date_present 封面落款含“YYYY年M月”报告日期（2026-10-21 新增）
    body_numbering    正文节含 <w:pgNumType w:start="1"/>（页码从 1 重起）
    toc_no_self_ref   目录未自收录（目录区不重复出现「目录」字样，启发式）
    no_flat_formula   无公式压平残留（已知形态清单）
    no_writer_markers 无写作标记残留（写作参考/数据参考/逐月参考/[FORMULA）
    ch5_narrative     第5章分析叙述段计数 ≥ 15（防「只有图表无文字」，2026-09-20 新增）
    ch5_531_leadin    5.3.1 表前结构：定义段（统计报告期内）＋式中＋引表句（如表5），
                      且「式中」与特殊用能注各恰 1 次（2026-10-08 新增，P1 只告警不阻断）
    ch2_22_structure  2.2 三段式结构：文字区须含「建筑面积」（逐栋段必填项）；
                      建筑表数 ≥1 且表号连续（表2.1、表2.2…）
                      （2026-10-13 改写：D 形态不再有「全院合计」独立段；P1 只告警不阻断）
    ch2_22_photos     2.2 图区一致性：图注段数 = 内嵌图片数，且图注编号自 图2.2 起连续
                      （2026-10-13 新增，专抓"清单缺条目 ⇒ 图注在、图不在"；P1 只告警不阻断）
    ch3_photos        第3章图区一致性：图注段数 = 内嵌图片数，且图注编号自 图3.1 起连续
                      （2026-10-13 新增；第3章照片是硬要求，漏写图注行会静默无图；P1 只告警不阻断）
    ch4_photos        第4章计量器具照片：至少 1 条 图4.x 图注、编号连续，
                      且每条图注前至少有 1 张图（允许一注多图；P1 只告警不阻断）
    ch5_figures       第5章图表：图注编号连续；有图图注前恰有 1 张图；
                      缺图图注须带可见“暂缺”说明；无落单图片
    ch4_structure     第4章小节结构：4.1/4.2/4.3 三节齐全、无 4.4、4.3 标题为「能源资源统计成效及问题」
                      （2026-10-13 新增；原「4.3 统计情况」已废止合并；P1 只告警不阻断）
    ch5_52_layout     5.2 版面：含图能源节① 首段有设备/系统描述 ② 两张图注不相邻
                      ③ 图注后接「由图…分析」句（2026-10-13 新增；P1 只告警不阻断）
    ch5_52_monthly    5.2.1 逐月段归因：写了「用电量较大月份」就必须有原因句
                      （2026-10-14 新增；P1 只告警不阻断）
    ch5_52_water      5.2.2 用水节：① 段1 与段4 的补水项必须一致（方案A 同源）
                       ② 异常说明段只允许出现「水」（禁跨能源串味）
                       ③ 禁系统字眼（平台登记/系统/数据来源）
                       （2026-10-15 新增；P1 只告警不阻断）
    num_style         正文数值与括号规范：① 禁「月份（数值）」形态 ② 禁设备名后括号塞台数/
                       参数 ③ 整数不带小数位（17622 不写 17622.00）④ 禁千分位
                       （2026-10-15 新增；P1 只告警不阻断）
    ch5_t51           表5.1 形态：① 首列斜线表头（w:tl2br + 两段文本）② 列序 电费/水费/
                       供暖费/油费/燃气费 ③ 数值整数不带小数位
                       （2026-10-16 新增，对齐莘县/淄博样板；P1 只告警不阻断）
    ch5_energy_leadin 5.2 各能源节段1：引语统一为「根据所提供能耗账单及缴费发票统计分析」，
                       数值与单位之间空一格（2026-10-16 新增；P1 只告警不阻断）
    ch5_trend_word    5.2 各节段2：趋势词须与"最大年变化率"四档口径一致
                       （方向优先；≤5% 基本稳定／≤10% 波动不大／≤15% 出现一定波动／>15% 波动较大）
                       （2026-10-16 新增；P1 只告警不阻断）
    ch5_525_fee       5.2 费用节五要素：引表句+引语统一／整体定性句（四档词）／逐年句带增减率且
                       条数 ≥ 表5.1 年数−1／段末引图句且图号对得上饼图图注
                       （2026-10-16 新增；P1 只告警不阻断）
    ch5_std_symbol    5.3 各节公式符号须与标准原文一致（Ejfgn／Ejd／Er／Ejngn，禁旧符号
                       Ejrcn／Eja／Egnm），式中措辞须写「单位为…」
                       （2026-10-16 新增；P1 只告警不阻断）
    ch5_53_conclusion 5.3 各指标表后结论段＝纯事实句：须含「分别为…」数值句、禁判词与建议
                       （节能空间/须整改/成效/压力/幅度约…）、跨档不得用「均」
                       （2026-10-19 新增，形态基准＝莘县样板；P1 只告警不阻断）
    ch5_532_note      5.3.2 标准注：医疗项目须有 DB37/T 2673-2019 §3.7 的注（含照明插座/空调/
                       电梯/水泵/通风机，不含特殊用能系统用电），且位置在「式中」之后；
                       党政/教育/政务标准无此注，不检查（2026-10-19 新增；P1 只告警不阻断）
    ch5_53_removal    5.3 剔除项：① 表5.2/表5.3 的「建筑面积」行须逐年同源（分母同一份值）
                       ② 表格内不得出现「剔除/扣除/扣减」行（只进后台计算，不进表格）
                       （2026-10-19 新增；P1 只告警不阻断）
    ch5_533_people    5.3.3 用能人数说明：医疗项目须有标准定义句 + 「平均用能人数」结果句，
                       禁四要素括号明细（明细归 2.1）（2026-10-19 新增；P1 只告警不阻断）
    ch5_534_water     5.3.4 单位开放床日用水量表：须有「全年实际开放床日数（床·日）」行、
                       首行用「年用水总量」、单位写 L/（床·日）（2026-10-20 新增；P1 只告警）
    --pdf 时另加 2 项:
    pdf_prebody_clean 正文前页面无页眉文字、无页脚数字
    pdf_footer_seq    正文页脚数字序列连续（从 1 起）

度量（总是输出）: oMath / captions / tables / drawings / media_files / ch5_body_paras
                  building_tables / building_tables_cols（建筑基本信息表数量与各表列数）
                  pages / prebody_pages / header_pages / footer_pages（需 --pdf；后三者=正文口径）
--expect 键: pages（容差 ±2）/ oMath / captions / tables / drawings / media_files
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

MARKERS = ["写作参考", "数据参考", "逐月参考", "[FORMULA"]
# 公式压平检测（2026-10-19 同步标准符号）：新符号 + 旧符号都留，两代写法被压平都能抓到。
# 背景：公式对象一旦被压平成纯文本，会变成 "Ejfgn=E−Egn−EjtM" 这类字符串（分式结构丢失）；
# 只按旧符号（Ejrcn/Eja/Egnm）检索时，改名后的公式压平将**静默通过**。
FLAT_FORMULAS = ["Ejfgn=E", "Ejd=ED", "Er=EP", "Vuc=Vk", "Ejngn=Egn",
                 "Ejrcn=E", "Eja=ED", "Egnm=Egn"]
# P1（2026-10-08 定）：只报告/告警，不阻断装配
P1_NONBLOCKING = {"ch5_531_leadin", "ch2_22_structure", "ch2_22_photos", "ch3_photos",
                  "ch4_photos", "ch4_structure", "ch5_52_layout", "ch5_52_monthly", "ch5_52_water",
                  "num_style", "ch5_t51", "ch5_energy_leadin", "ch5_trend_word",
                  "ch5_525_fee", "ch5_std_symbol", "ch5_53_conclusion", "ch5_532_note",
                  "ch5_53_removal", "ch5_533_people", "ch5_534_water"}
# 公共建筑族：下列检查是公共机构专属口径，按族跳过
PUBLIC_BUILDING_SKIP = {
    "ch4_photos", "ch4_structure", "ch5_531_leadin", "ch5_52_layout", "ch5_52_water",
    "ch5_t51", "ch5_energy_leadin", "ch5_trend_word", "ch5_525_fee",
    "ch5_std_symbol", "ch5_532_note", "ch5_53_removal", "ch5_533_people",
    "ch5_534_water", "apx2_table",
}
PUBLIC_BUILDING_P1 = {
    "pb_ch2_title", "pb_ch6_structure", "pb_ch5_metrics",
    "pb_coefficient", "pb_appendix2", "pb_no_public_institution",
}
P1_NONBLOCKING |= PUBLIC_BUILDING_P1


def detect_family(docx_path: str) -> str:
    p = Path(docx_path).resolve()
    for parent in [p.parent, *p.parents]:
        data_path = parent / "data.json"
        if not data_path.is_file():
            continue
        try:
            with open(data_path, encoding="utf-8") as fh:
                raw = json.load(fh)
            if str((raw.get("base") or {}).get("unit_type") or "") == "公共建筑":
                return "public_building"
        except (OSError, json.JSONDecodeError):
            pass
        break
    return "public_institution"


def public_building_checks(text: str):
    tn = norm(text)
    checks = {
        "pb_ch2_title": ("第2章建筑概况" in tn and "公共机构概况" not in tn),
        "pb_ch6_structure": all(
            x in tn for x in ("6.1用电系统运行分析", "6.2用水系统运行分析", "6.3其他用能系统运行分析")
        ),
        "pb_ch5_metrics": ("5.3.1" in tn and "5.3.3" in tn
                           and "单位建筑面积非供暖能耗" not in tn),
        "pb_coefficient": ("0.1229" in tn and "0.31" not in tn),
        "pb_appendix2": ("附录2" in tn and "各种能源折标准煤参考系数" in tn and "0.1229" in tn),
        "pb_no_public_institution": ("公共机构概况" not in tn and "非供暖能耗" not in tn),
    }
    details = {}
    if not checks["pb_ch2_title"]:
        details["pb_ch2_title"] = "第2章应为「建筑概况」，且不得出现「公共机构概况」"
    if not checks["pb_ch6_structure"]:
        details["pb_ch6_structure"] = "第6章应为 6.1 用电 / 6.2 用水 / 6.3 其他"
    if not checks["pb_ch5_metrics"]:
        details["pb_ch5_metrics"] = "5.3 指标节不足，或出现公共机构「非供暖能耗」口径"
    if not checks["pb_coefficient"]:
        details["pb_coefficient"] = "电力折标应为 0.1229，且不得出现 0.31"
    if not checks["pb_appendix2"]:
        details["pb_appendix2"] = "附录2 应为折标系数表且含 0.1229"
    if not checks["pb_no_public_institution"]:
        details["pb_no_public_institution"] = "正文出现公共机构专属章名/指标名"
    return checks, details
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".emf", ".wmf", ".tif", ".tiff")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def visible_text(doc_xml: str) -> str:
    x = re.sub(r"<w:tab[^>]*/>", " ", doc_xml)
    x = re.sub(r"<w:br[^>]*/>", " ", x)
    return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", x))


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def count_captions(doc_xml: str) -> int:
    """图注计数：按段落拼接全部 w:t 后判定（Word 保存会重排 run 分割，
    不能用单 w:t 正则，否则收尾后计数误报 0）。"""
    n = 0
    for m in re.finditer(r"<w:p[ >].*?</w:p>", doc_xml, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(0)))
        if re.match(r"图\d+\.\d+", re.sub(r"\s+", "", t)):
            n += 1
    return n


def ch5_narrative_count(doc_xml: str) -> int:
    """第5章分析叙述段计数（2026-09-20 新增）：剔表格/标题/图注表题后，≥12 字段落数。

    区间 = 正文中最后一次「第5章」标题之后、其后首个「第6章」标题之前
    （目录区条目早于正文标题，天然被排除）。"""
    x = re.sub(r"<w:tbl[ >].*?</w:tbl>", " ", doc_xml, flags=re.S)
    paras = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>", x, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(0)))
        paras.append(re.sub(r"\s+", "", t))
    idx5 = None
    for i, t in enumerate(paras):
        if t.startswith("第5章"):
            idx5 = i
    if idx5 is None:
        return 0
    idx6 = len(paras)
    for j in range(idx5 + 1, len(paras)):
        if paras[j].startswith("第6章"):
            idx6 = j
            break
    n = 0
    for t in paras[idx5 + 1:idx6]:
        if len(t) < 12:
            continue
        if re.match(r"^\d+\.\d+", t):       # 小节标题
            continue
        if re.match(r"^[图表]\s*\d", t):     # 图注/表题
            continue
        n += 1
    return n


def ch5_531_leadin_ok(doc_xml: str):
    """5.3.1 表格前结构（2026-10-08 定，形态基准＝莘县行政审批服务局样板）。

    区间 = 正文「5.3.1」标题 → 其后第一张表。要求同时具备：
      ① 定义段（含「统计报告期内」）② 符号段（含「式中」）③ 引表句（含「如表5」）
    防重复：区间内「式中」恰 1 次、特殊用能注恰 1 条。
    分级 P1：只报告，不阻断装配。
    """
    blocks = re.findall(r"<w:p[ >].*?</w:p>|<w:tbl>.*?</w:tbl>", doc_xml, re.S)

    def _ptext(b: str) -> str:
        return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", b))

    cands = [i for i, b in enumerate(blocks)
             if b.startswith("<w:p") and "5.3.1" in norm(_ptext(b))]
    if not cands:
        return False, "未找到含 5.3.1 的段落"
    head = None
    for i in cands:
        m = re.search(r'w:pStyle[^>]*w:val="([^"]*)"', blocks[i])
        style = m.group(1) if m else ""
        if "eading" in style or "标题" in style:
            head = i
            break
    if head is None:                      # 退路：取最后一个（目录条目在前）
        head = cands[-1]
    texts, j = [], head + 1
    while j < len(blocks) and not blocks[j].startswith("<w:tbl"):
        texts.append(_ptext(blocks[j]))
        j += 1
    if j >= len(blocks):
        return False, "5.3.1 之后未找到数据表"
    region = norm("".join(texts))
    miss = []
    if "统计报告期内" not in region:
        miss.append("缺定义段（未含「统计报告期内」）")
    if "式中" not in region:
        miss.append("缺符号段（未含「式中」）")
    if "如表5" not in region:
        miss.append("缺引表句（未含「如表5…所示：」）")
    if region.count("式中") > 1:
        miss.append("「式中」出现 %d 次（应 1 次，疑脚本公式与写作层公式重复）" % region.count("式中"))
    # 特殊用能注按「段」计、不挑措辞：段落以「注：」开头且提到「特殊用能」或「特定功能」。
    # 车库注（只提车库）与项目特有的数据缺口注（如供暖未计量）都不计入。
    n_note = sum(1 for t in texts
                 if "注：" in norm(t) and ("特殊用能" in norm(t) or "特定功能" in norm(t)))
    if n_note != 1:
        miss.append("特殊用能注 %d 条（应恰 1 条）" % n_note)
    if miss:
        return False, "；".join(miss)
    return True, ""


def _ptext(block: str) -> str:
    """段落/表格块里的可见文本（拼接全部 w:t）。"""
    return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", block))


def _pstyle(block: str) -> str:
    m = re.search(r'w:pStyle[^>]*w:val="([^"]*)"', block)
    return (m.group(1) if m else "") or ""


def ch2_22_region(doc_xml: str):
    """2.2 建筑物概况 区间：标题之后 → 下一个标题（2.3/第N章/附录/任何 Heading）之前。

    目录缓存条目（pStyle 以 toc 开头）不计入，避免目录里的「2.2 …」被当成正文标题。
    """
    blocks = re.findall(r"<w:p[ >].*?</w:p>|<w:tbl>.*?</w:tbl>", doc_xml, re.S)
    start = None
    for i, b in enumerate(blocks):
        if not b.startswith("<w:p"):
            continue
        style = _pstyle(b)
        if style.lower().startswith("toc"):
            continue
        t = norm(_ptext(b))
        if start is None:
            if t.startswith("2.2") and "建筑物概况" in t:
                start = i
            continue
        if (t.startswith("2.3") or re.match(r"^(第\d+章|附录)", t)
                or style.lower().startswith("heading")):
            return blocks[start + 1:i]
    return blocks[start + 1:] if start is not None else []


def _chapter_region(doc_xml: str, chapter_no: int):
    """第 N 章区间：正文「第N章 …」标题之后 → 下一个「第N+1章」/「附录」之前。

    目录缓存条目（pStyle 以 toc 开头）不计入，避免目录里的章名被当成正文标题。
    """
    blocks = re.findall(r"<w:p[ >].*?</w:p>|<w:tbl>.*?</w:tbl>", doc_xml, re.S)
    self_pat = re.compile(r"^第%d章" % chapter_no)
    next_pat = re.compile(r"^第\d+章|^附录")
    start = None
    for i, b in enumerate(blocks):
        if not b.startswith("<w:p"):
            continue
        if _pstyle(b).lower().startswith("toc"):
            continue
        t = norm(_ptext(b))
        if start is None:
            if self_pat.match(t):
                start = i
            continue
        if next_pat.match(t) and not self_pat.match(t):
            return blocks[start + 1:i]
    return blocks[start + 1:] if start is not None else []


def ch2_22_structure_ok(doc_xml: str):
    """2.2 三段式结构（2026-10-13 改写）。

    参考口径 = 参考报告《日照市岚山区人民医院能源审计报告》2.2 的三段式
    （文字区 → 图区 → 表区），据此本检查只看两件事：
      ① 文字区含「建筑面积」（逐栋段必填项，读者不看表即可核对）
      ② 建筑基本信息表 ≥1 张，且表号连续（表2.1、表2.2…），表号数 = 表数
    已废止的旧口径：要求「全院合计」独立成段（D 形态没有这句）。
    分级 P1：只报告，不阻断装配。
    """
    region = ch2_22_region(doc_xml)
    if not region:
        return False, "未定位到 2.2 建筑物概况 区间"
    texts = norm("".join(_ptext(b) for b in region))
    miss = []
    if "建筑面积" not in texts:
        miss.append("逐栋段缺必填项「建筑面积」")
    nums = []
    for b in region:
        m = re.match(r"表2\.(\d+)", norm(_ptext(b)))
        if m:
            nums.append(int(m.group(1)))
    tables = sum(1 for b in region
                 if b.startswith("<w:tbl") and "建筑物名称" in _ptext(b)[:60])
    if tables == 0:
        miss.append("区间内没有建筑基本信息表")
    if nums and tables and len(nums) != tables:
        miss.append("表题 %d 条 ≠ 建筑表 %d 张" % (len(nums), tables))
    if nums != list(range(1, len(nums) + 1)):
        miss.append("表号不连续：%s" % nums)
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch2_22_photos_ok(doc_xml: str):
    """2.2 图区一致性（2026-10-13 新增，P1 只告警）。

    专抓两类只在成品里才看得出的问题：
      ① 图注段数 ≠ 内嵌图片数——装配对"清单缺条目"只打 WARN，图注照写进正文、
         图不出现，报告可以一路绿灯交付；
      ② 图注编号不连续（应自 图2.2 起连号；图2.1 属 2.1 节，不计入本区间）。
    """
    region = ch2_22_region(doc_xml)
    if not region:
        return False, "未定位到 2.2 建筑物概况 区间"
    nums, imgs = [], 0
    for b in region:
        if not b.startswith("<w:p"):
            continue
        m = re.match(r"图2\.(\d+)", norm(_ptext(b)))
        if m:
            nums.append(int(m.group(1)))
        if ("<w:drawing" in b) or ("<w:pict" in b):
            imgs += 1
    if not nums and imgs == 0:
        return True, ""
    miss = []
    if len(nums) != imgs:
        miss.append("图注 %d 条 ≠ 图片 %d 张（清单缺条目时装配只打 WARN，图不会出现）"
                    % (len(nums), imgs))
    if nums and nums != list(range(2, 2 + len(nums))):
        miss.append("图注编号不连续：%s（应自 图2.2 起连号）" % nums)
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch3_photos_ok(doc_xml: str):
    """第3章图区一致性（2026-10-13 新增，P1 只告警）。

    ① 图注段数 = 内嵌图片数（防"图注在、图不在"）；
    ② 图注编号自 图3.1 起连续。

    背景：第3章照片是规则**硬要求**（管理文件截图 / 荣誉证书，见 chapter-guides-1-4.md
    「图片路由」），但装配端只认 md 图注行——漏写就静默无图。实测岚山区人民医院：
    `es` 里有 2 张可用照片，ch3.md 一条图注行都没有，新旧两版交付件 3.2/3.3 全无图。
    """
    region = _chapter_region(doc_xml, 3)
    if not region:
        return False, "未定位到 第3章 区间"
    nums, imgs = [], 0
    for b in region:
        if not b.startswith("<w:p"):
            continue
        m = re.match(r"图3\.(\d+)", norm(_ptext(b)))
        if m:
            nums.append(int(m.group(1)))
        if ("<w:drawing" in b) or ("<w:pict" in b):
            imgs += 1
    if not nums and imgs == 0:
        return True, ""
    miss = []
    if len(nums) != imgs:
        miss.append("图注 %d 条 ≠ 图片 %d 张（清单缺条目时装配只打 WARN，图不会出现）"
                    % (len(nums), imgs))
    if nums and nums != list(range(1, 1 + len(nums))):
        miss.append("图注编号不连续：%s（应自 图3.1 起连号）" % nums)
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch4_photos_ok(doc_xml: str):
    """第4章计量器具照片一致性（P1 只告警）。

    第4章允许一个 `图4.N 计量器具照片` 下连续放多张照片，因此不能套用
    “图注数 = 图片数”；这里检查每条图注前至少有 1 张图，并校验编号连续。
    """
    region = _chapter_region(doc_xml, 4)
    if not region:
        return False, "未定位到 第4章 区间"
    nums, missing, pending_imgs, total_imgs = [], [], 0, 0
    for b in region:
        if not b.startswith("<w:p"):
            continue
        has_img = ("<w:drawing" in b) or ("<w:pict" in b)
        text = norm(_ptext(b))
        m = re.match(r"图4\.(\d+)", text)
        if m:
            nums.append(int(m.group(1)))
            if pending_imgs == 0:
                missing.append("图4.%s" % m.group(1))
            pending_imgs = 0
        elif has_img:
            pending_imgs += 1
            total_imgs += 1
    miss = []
    if not nums:
        miss.append("第4章没有任何 图4.x 计量器具照片图注")
    if nums and total_imgs == 0:
        miss.append("第4章有图注但没有内嵌图片")
    if missing:
        miss.append("以下图注前没有图片：%s" % "、".join(missing))
    if nums and nums != list(range(1, len(nums) + 1)):
        miss.append("图注编号不连续：%s（应自 图4.1 起连号）" % nums)
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch5_figures_ok(doc_xml: str):
    """第5章图表一致性：有图时一注一图；缺图须有可见“暂缺”说明。"""
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    nums, missing, extra = [], [], []
    pending_imgs = 0
    total_imgs = 0
    total_placeholders = 0
    for block in region:
        if not block.startswith("<w:p"):
            continue
        has_img = ("<w:drawing" in block) or ("<w:pict" in block)
        raw_text = _ptext(block).strip()
        match = re.match(r"图5\.(\d+)(?=\s|$)", raw_text)
        if match:
            nums.append(int(match.group(1)))
            is_placeholder = bool(re.search(r"（暂缺[：:].+）$", raw_text))
            if is_placeholder:
                total_placeholders += 1
            elif pending_imgs == 0:
                missing.append(f"图5.{match.group(1)}")
            elif pending_imgs > 1:
                extra.append(f"图5.{match.group(1)}前 {pending_imgs} 张")
            pending_imgs = 0
        elif has_img:
            pending_imgs += 1
            total_imgs += 1
    if pending_imgs:
        extra.append(f"末条图注后有 {pending_imgs} 张未配对图片")
    miss = []
    if not nums:
        miss.append("第5章没有任何 图5.x 图注")
    if nums and total_imgs == 0 and total_placeholders == 0:
        miss.append("第5章有图注但没有内嵌图片")
    if missing:
        miss.append("以下图注前没有图片：" + "、".join(missing))
    if extra:
        miss.append("以下图注前图片数量不是 1 张：" + "、".join(extra))
    if nums and nums != list(range(1, len(nums) + 1)):
        miss.append(f"图注编号不连续：{nums}（应自 图5.1 起连号）")
    if miss:
        return False, "；".join(miss)
    return True, ""


def _heading_style_ids(z) -> set:
    """从 styles.xml 取「样式名以 Heading 开头」的 styleId 集合。

    注意：段落里 `w:pStyle w:val` 存的是 **styleId**（本项目实测是数字如 "21"），
    不是样式名 "Heading 2"——所以必须回查 styles.xml 的 id→name 映射。
    """
    ids = set()
    try:
        s = z.read("word/styles.xml").decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ids
    for m in re.finditer(r"<w:style\b.*?</w:style>", s, re.S):
        blk = m.group(0)
        sid = re.search(r'w:styleId="([^"]*)"', blk)
        name = re.search(r'<w:name w:val="([^"]*)"', blk)
        if sid and name and name.group(1).lower().startswith("heading"):
            ids.add(sid.group(1))
    return ids


def ch4_structure_ok(doc_xml: str, heading_ids=None):
    """第4章小节结构（2026-10-13 新增，P1 只告警）。

    第4章**只三节**：4.1 能源资源计量体系 / 4.2 计量器具配备及管理 /
    **4.3 能源资源统计成效及问题**（依据参考报告《日照市岚山区人民医院能源审计报告》）。
    检查三件事：
      ① 4.1 / 4.2 / 4.3 三个小节标题都在；
      ② **不得出现已废止的 4.4**（原「4.3 统计情况 + 4.4 成效及问题」两节已合并）；
      ③ 4.3 标题须是「能源资源统计成效及问题」（不是「统计情况」）。
    """
    region = _chapter_region(doc_xml, 4)
    if not region:
        return False, "未定位到 第4章 区间"
    titles = {}
    for b in region:
        if not b.startswith("<w:p"):
            continue
        style = _pstyle(b)
        if heading_ids is not None:
            if style not in heading_ids:             # 只认标题样式（styles.xml 映射后的 id）
                continue
        elif style.lower().startswith("toc"):
            continue                                  # 无 styles 映射时：至少排除目录条目
        t = norm(_ptext(b))
        m = re.match(r"^(4\.\d)\s*(.*)$", t)
        if m and len(t) <= 24:
            titles.setdefault(m.group(1), m.group(2))
    if not titles:
        return False, "第4章区间内未识别到 4.x 小节标题"
    miss = []
    for k in ("4.1", "4.2", "4.3"):
        if k not in titles:
            miss.append("缺小节 %s" % k)
    if "4.4" in titles:
        miss.append("出现已废止的 4.4 节（第4章应只有三节）")
    if "4.3" in titles and "统计成效" not in titles["4.3"]:
        miss.append("4.3 标题应为「能源资源统计成效及问题」，实际「%s」" % titles["4.3"])
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch5_52_layout_ok(doc_xml: str, heading_ids=None):
    """第5章 5.2 版面（2026-10-13 新增，P1 只告警）。

    背景：5.2 的"四段两图、图文交替"以前只写在规则里、没有任何检查——实测四份报告里
    三份照做、岚山区人民医院那份把段1+段2、段3+段4 各压成一段（4 段变 2 段），
    于是**设备列举丢失、两张图注相邻**，却能一路绿灯交付。

    检查（只对**含图的能源节**生效；5.2.4 其他用能无图不查）：
      ① 首段须含设备/系统描述（设备/系统/台/套/机组/锅炉 任一），防"只写数值"；
      ② 两张图注不得相邻（图注行之间必须夹着正文段）；
      ③ 图注之后紧邻的正文段须以"由图5.X分析"开头。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"

    def _is_head(b):
        if not b.startswith("<w:p"):
            return False
        if heading_ids is not None:
            return _pstyle(b) in heading_ids
        return not _pstyle(b).lower().startswith("toc")

    start = end = None
    for i, b in enumerate(region):
        if not _is_head(b):
            continue
        t = norm(_ptext(b))
        if start is None and re.match(r"^5\.2", t):
            start = i
        elif start is not None and re.match(r"^5\.3", t):
            end = i
            break
    if start is None:
        return False, "未定位到 5.2 小节"
    seg = region[start + 1:(end if end is not None else len(region))]

    sub_blocks, cur_title, cur_items = [], "(未命名小节)", []
    for b in seg:
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        if _is_head(b) and re.match(r"^5\.2\.\d", t):
            sub_blocks.append((cur_title, cur_items))
            cur_title, cur_items = t, []
            continue
        if not t:
            continue          # 空文本段（图片段本身无文字）不参与"图注是否相邻"的判断
        cur_items.append(("fig" if re.match(r"^图5\.\d", t) else "p", t))
    sub_blocks.append((cur_title, cur_items))

    # 段1 的"设备/系统描述"关键词（含用热节的"供热/供暖/热源"等，避免误报）
    DEV_WORDS = ("设备", "系统", "机组", "锅炉", "空调", "照明", "水泵", "供水", "给水",
                 "供热", "供暖", "热源", "冷源", "配电", "车辆", "灶")
    miss = []
    for title, items in sub_blocks:
        if "费用" in title:                # 费用节固定最后（表5.1 + 各年饼图），不适用本检查
            continue
        if not any(k == "fig" for k, _t in items):
            continue                       # 无图节（其他用能）不查
        first = next((t for k, t in items if k == "p" and t), "")
        if not any(w in first for w in DEV_WORDS):
            miss.append("%s：首段缺设备/系统描述" % title)
        for i in range(1, len(items)):
            if items[i][0] == "fig" and items[i - 1][0] == "fig":
                miss.append("%s：两张图注相邻（%s / %s）"
                            % (title, items[i - 1][1][:16], items[i][1][:16]))
                break
        # 只查**第一个**图注之后：规范要求"段2 以「由图5.X分析」开头"
        # （后一个图注之后是段4 归因段，样板里"综合分析，…"等写法并存，不强制由图开头）
        for i, (k, _t) in enumerate(items):
            if k != "fig":
                continue
            nxt = next((t for k2, t in items[i + 1:] if k2 == "p" and t), "")
            if nxt and not nxt.startswith("由图"):
                miss.append("%s：首个图注后未接“由图…分析”句（实际“%s”）" % (title, nxt[:16]))
            break
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch5_52_monthly_ok(doc_xml: str, heading_ids=None):
    """5.2.1 逐月段归因（2026-10-14 新增，P1 只告警）。

    判定表（chapter5-templates.md 5.2 节）要求：有“月份首句”时必须给出原因句。
    检查：5.2.1 区间内含「用电量较大月份」时，区间内须命中归因关键词之一——
    「结合制冷空调形式分析」/「冬季以」/「热源为」/「虽然…供暖」/「部分房间使用分体空调供暖」/
    「其他供暖形式设备」；否则视为“只有月份、没有原因”。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    start = end = None
    for i, b in enumerate(region):
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        if heading_ids is not None and _pstyle(b) not in heading_ids:
            continue
        if start is None and re.match(r"^5\.2\.1", t):
            start = i
        elif start is not None and re.match(r"^5\.2\.2", t):
            end = i
            break
    if start is None:
        return True, ""                      # 无 5.2.1（如水/气单能源项目）→ 不检查
    seg = region[start + 1:(end if end is not None else len(region))]
    text = "".join(_ptext(b) for b in seg)
    if "用电量较大月份" not in norm(text):
        return True, ""                      # 没写月份首句 → 不检查
    keys = ("结合制冷空调形式分析", "冬季以", "热源为", "虽然是市政供暖",
            "部分房间使用分体空调供暖", "其他供暖形式设备")
    if any(k in text for k in keys):
        return True, ""
    return False, "5.2.1 写了“用电量较大月份”但缺少原因句（判定表要求供冷句/供热句至少其一）"


def _narrative_paras(doc_xml: str):
    """正文叙述段（跳过表格、目录、图注里的"（单位：…）"由调用方自行处理）。"""
    out = []
    for b in re.finditer(r"<w:p[ >].*?</w:p>", doc_xml, flags=re.S):
        blk = b.group(0)
        t = norm(_ptext(blk))
        if t:
            out.append(t)
    return out


NUM_STYLE_BANS = (
    ("月份后括号数值", re.compile(r"\d{1,2}月\s*（\s*[\d一二三四五六七八九十]"),
     "写成「{年}{月}用水量/用电量为{值}，较…高出{X}%」，数值与百分比都进正文"),
    ("设备名后括号台数/参数", re.compile(r"（[^）]{0,30}\d+\s*(?:台|套|个|组)[^）]{0,30}）"),
     "改写成分句：「…其中{设备}N台，供{区域}使用，运行时间为…」"),
    # ★2026-10-16 补盲区：正文括号里塞统计数值（金额/占比/用量）也属违规——《3b》规定
    # 正文括号只允许三类（单位 / 标准编号 / 图注「（单位：…）」）。实测漏网形态：
    # 「其中电费占比最高（2024年377.05万元，占71.1%）」。排除标准号与「（单位：…）」。
    ("括号承载统计数值", re.compile(
        r"（(?![^）]*（单位：)(?![^）]*(?:DB|GB|JGJ|CJJ)[/T])"
        r"[^）]{0,40}?\d+(?:\.\d+)?\s*(?:万元|元|kWh|m³|GJ)(?![a-zA-Z])[^）]{0,40}?）"),
     "把括号拆成正文分句：「…其中电费占比最高，2024年电费为X万元，占当年总额的Y%」"),
    ("整数带无意义小数位", re.compile(r"(?<![\d.])\d{2,}\.0+(?![\d])"),
     "整数不带小数位（17622 不写 17622.00；5090273 不写 5090273.00）"),
    ("千分位分隔符", re.compile(r"\d{1,3}(?:,\d{3})+"),
     "全文禁千分位（写 1762200，不写 1,762,200）"),
)


# 趋势词四档（chapter5-spec.md《段2详细规范·2.1》，2026-10-16 用户定）
TREND_CLASSES = {
    "up": ("逐年上升", "逐年增长", "逐年持续增长", "呈上升趋势", "呈逐年上升趋势"),
    "down": ("逐年下降", "逐年递减", "逐年降低", "逐年持续下降", "呈下降趋势", "呈逐年下降趋势"),
    "big": ("波动较大", "出现较大波动"),          # 注意顺序：先判"波动较大"，再判"波动不大"
    "small": ("出现一定波动", "小幅波动", "有一定波动"),
    "noswing": ("波动不大", "变化不大"),
    "stable": ("基本稳定", "基本持平", "保持稳定"),
}
# 逐年率写法实测有多种："增长率为2.7%" / "降幅为7.5%" / "增幅19.71%" / "降低率5.72%"
RATE_RE = re.compile(r"(增长|增加|上升|升|降低|减少|下降|降)(?:率|幅)?为?\s*([\d.]+)\s*%")
_UP_WORDS = ("增长", "增加", "上升", "升")


def _trend_expected(rates):
    """按口径算趋势类：全增→up、全减→down，否则按最大绝对值（≤5/≤10/≤15/>15）。"""
    if rates and all(r > 0 for r in rates):
        return "up"
    if rates and all(r < 0 for r in rates):
        return "down"
    m = max((abs(r) for r in rates), default=0.0)
    if m <= 5:
        return "stable"
    if m <= 10:
        return "noswing"
    if m <= 15:
        return "small"
    return "big"


FEE_TREND_WORDS = ("基本稳定", "波动不大", "出现一定波动", "波动较大",
                   "整体呈逐年上升趋势", "整体呈逐年下降趋势")


# 5.3 结论段禁词（2026-10-19 用户定：纯事实句，判词与建议归第7章）
CONCL_BANNED = ("节能空间", "须重点说明", "整改", "成效", "压力", "潜力", "幅度约", "短板", "差距", "建议")


def ch5_532_note_ok(doc_xml: str, heading_ids=None):
    """5.3.2 标准注（2026-10-19 新增，P1 只告警）。

    口径：DB37/T 2673-2019 §3.7 有注——「注：医疗机构常规用能系统电耗包括照明插座用电、
    空调用电、电梯用电、水泵用电、通风机用电等。不包括特殊用能系统中的用电。」
    党政 2672 / 教育 2671 / 政务 3781 的同类条款**无注**，故只在医疗项目检查。
    位置：必须在「式中」之后（写作层易把它贴到节首）。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    subs, cur = {}, None
    for b in region:
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        is_head = heading_ids is None or _pstyle(b) in heading_ids
        m = re.match(r"^(5\.3\.\d+)", t) if is_head else None
        if m:
            cur = m.group(1)
            subs[cur] = []
            continue
        if cur:
            subs[cur].append(_ptext(b))
    paras = subs.get("5.3.2") or []
    if not paras:
        return True, ""                      # 无 5.3.2（项目无电耗指标）→ 不检查
    text = "".join(paras)
    if "医疗机构常规用能系统" not in text:
        return True, ""                      # 非医疗项目（2672/2671/3781 无此注）→ 不检查
    key = "注：医疗机构常规用能系统电耗包括照明插座用电"
    if key not in text:
        return False, "5.3.2 缺标准注（DB37/T 2673-2019 §3.7：说明含哪些用电、不含特殊用能系统用电）"
    i_note, i_sz = text.find(key), text.find("式中")
    if i_sz >= 0 and i_note < i_sz:
        return False, "5.3.2 标准注位置错（应在「式中」之后、引表句之前）"
    return True, ""


REMOVAL_ROW_KEYS = ("剔除", "扣除", "扣减")


def ch5_53_removal_ok(doc_xml: str, heading_ids=None):
    """5.3 剔除项（2026-10-19 新增，P1 只告警）。

    口径（用户 2026-10-19 定）：特殊设备用电／本年新建施工用电／交通电／地下车库面积
    只在后台参与计算，**表格里不得出现扣减行**；且 5.3.1 与 5.3.2 的「建筑面积」行
    必须同源（逐年逐值相等，分母同一份值）。
    文档层只能查这两件事；分子是否真扣由 indicators 单测覆盖。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    bad, areas, cur = [], {}, None
    for b in region:
        if b.startswith("<w:p"):
            t = norm(_ptext(b))
            is_head = heading_ids is None or _pstyle(b) in heading_ids
            m = re.match(r"^(5\.3\.\d+)", t) if is_head else None
            if m:
                cur = m.group(1)
            continue
        if not b.startswith("<w:tbl") or not cur:
            continue
        for tr in re.findall(r"<w:tr[ >].*?</w:tr>", b, flags=re.S):
            cells = [norm(re.sub(r"<[^>]+>", "", c))
                     for c in re.findall(r"<w:tc>.*?</w:tc>", tr, flags=re.S)]
            if not cells:
                continue
            label = cells[0]
            if any(k in label for k in REMOVAL_ROW_KEYS):
                bad.append(f"{cur} 表格出现扣减行「{label}」（剔除项只进后台计算）")
            # 只认「建筑面积（m²）」这一行；「单位建筑面积…」是指标行，不是分母
            if (label.startswith("建筑面积") and "单位" not in label
                    and cur in ("5.3.1", "5.3.2")):
                areas[cur] = cells[1:]
    a1, a2 = areas.get("5.3.1"), areas.get("5.3.2")
    if a1 and a2 and a1 != a2:
        bad.append("5.3.1 与 5.3.2 的建筑面积行不同源（%s vs %s）"
                   % ("/".join(a1), "/".join(a2)))
    if bad:
        return False, "；".join(bad[:4])
    return True, ""


def ch5_533_people_ok(doc_xml: str, heading_ids=None):
    """5.3.3 用能人数说明段（2026-10-19 新增，P1 只告警）。

    口径（用户 2026-10-19 定，按定额标准句式）：
      ① 医疗项目须有「医疗机构用能人数包括在岗在编的人员、各类编外工作人员、门诊人数、床位数」定义句；
      ② 结果句须写「平均用能人数」（`clinic_num`＝日均门诊人次）；
      ③ 禁止四要素括号明细（"（在岗职工…、床位…张）"量纲混用，明细归 2.1）。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    paras, cur = [], None
    for b in region:
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        is_head = heading_ids is None or _pstyle(b) in heading_ids
        m = re.match(r"^(5\.3\.\d+)", t) if is_head else None
        if m:
            cur = m.group(1)
            continue
        if cur == "5.3.3":
            paras.append(t)
    if not paras:
        return True, ""                      # 无 5.3.3（不生成人均指标）→ 不检查
    text = "".join(paras)
    if "医疗机构" not in text:
        return True, ""                      # 非医疗项目 → 不检查
    bad = []
    if "用能人数包括" not in text:
        bad.append("5.3.3 缺用能人数构成定义句（「医疗机构用能人数包括…」）")
    if "平均用能人数" not in text:
        bad.append("5.3.3 未写「平均用能人数」（clinic_num 为日均门诊人次）")
    if re.search(r"[（(]\s*在岗", text):
        bad.append("5.3.3 出现四要素括号明细（量纲混用，明细归 2.1）")
    if bad:
        return False, "；".join(bad)
    return True, ""


def ch5_534_water_ok(doc_xml: str, heading_ids=None):
    """5.3.4 单位开放床日用水量表（2026-10-20 新增，P1 只告警）。

    口径（用户 2026-10-20 定，对齐 DB37/T 4452-2021 式(5)）：
      ① 表内须有「全年实际开放床日数（床·日）」行，读者可用表内两行复算指标；
      ② 行名用「年用水总量」（W_z 口径），不再用「取水量」；
      ③ 单位统一写 `L/（床·日）`，禁止 `L/床·d`。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    paras, raw, tbl, cur = [], [], None, None
    for b in region:
        if b.startswith("<w:p"):
            t = norm(_ptext(b))
            is_head = heading_ids is None or _pstyle(b) in heading_ids
            m = re.match(r"^(5\.3\.\d+)", t) if is_head else None
            if m:
                cur = m.group(1)
                continue
            if cur == "5.3.4":
                paras.append(t)
                raw.append(b)
        elif b.startswith("<w:tbl") and cur == "5.3.4" and tbl is None:
            tbl = b
    text = "".join(paras)
    if "单位开放床日用水量" not in text:
        return True, ""                      # 非医疗取水口径 → 不检查
    if not tbl:
        return False, "5.3.4 缺计算表"
    labels, cells_all = [], []
    for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tbl, flags=re.S):
        cells = [norm(re.sub(r"<[^>]+>", "", c))
                 for c in re.findall(r"<w:tc>.*?</w:tc>", tr, flags=re.S)]
        if cells:
            labels.append(cells[0])
            cells_all.extend(cells)
    bad = []
    if not any("全年实际开放床日数" in l for l in labels):
        bad.append("5.3.4 表缺「全年实际开放床日数（床·日）」行（无法复算指标）")
    if not any(l.startswith("年用水总量") for l in labels):
        bad.append("5.3.4 表首行应改为「年用水总量（m³）」（对齐 W_z）")
    i_adv = next((i for i, l in enumerate(labels) if "先进值" in l), None)
    i_gen = next((i for i, l in enumerate(labels) if "通用值" in l), None)
    if i_adv is not None and i_gen is not None and i_adv > i_gen:
        bad.append("5.3.4 定额行序错：先进值应在通用值之前")
    joined = text + "".join(cells_all)
    if "L/（床·日）" not in joined:
        bad.append("5.3.4 单位须写「L/（床·日）」")
    if re.search(r"L/床·d", joined):
        bad.append("5.3.4 出现旧写法「L/床·d」")
    if "第i日的实际开放床日数" not in text:
        bad.append("5.3.4 式中缺标准变量 N_i（「第 i 日的实际开放床日数」）")
    if "单位换算系数" in text:
        bad.append("5.3.4 式中不得单列「10³——单位换算系数」（标准未列）")
    if re.search(r"Σ\s*N", text):
        bad.append("5.3.4 不得把 ΣN_i 当变量定义（求和已在公式中表达）")
    omml = "".join(re.findall(r"<m:oMath[ >].*?</m:oMath>", "".join(raw), flags=re.S))
    nary = re.findall(r"<m:nary>.*?</m:nary>", omml, flags=re.S)
    if not any("365" in re.sub(r"<[^>]+>", "", n) for n in nary):
        bad.append("5.3.4 公式分母应为 Σ(i=1→365) N_i（缺求和上下限）")
    if bad:
        return False, "；".join(bad)
    return True, ""


def ch5_53_conclusion_ok(doc_xml: str, heading_ids=None):
    """5.3 各指标表后结论段＝纯事实句（2026-10-19 新增，P1 只告警）。

    口径（形态基准＝莘县样板四节，均为一句话）：
      ① 表后必须有一句「…分别为v1、v2、v3…」的数值句；
      ② 禁判词与建议（节能空间／须重点说明／整改／成效／压力／潜力／幅度约／短板／差距／建议）
         —— 判词与整改建议归第7章，构成分析归第6章；
      ③ 三年同档才可用「均」：表内「评价结果」行若逐年不同，结论段出现「均」即告警。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    bad = []
    cur = None
    for i, b in enumerate(region):
        if b.startswith("<w:p"):
            t = norm(_ptext(b))
            is_head = heading_ids is None or _pstyle(b) in heading_ids
            m = re.match(r"^(5\.3\.\d+)", t) if is_head else None
            if m:
                cur = m.group(1)
            continue
        if not b.startswith("<w:tbl") or not cur:
            continue
        # 表后第一段非空正文 = 结论段
        concl = ""
        for b2 in region[i + 1:]:
            if not b2.startswith("<w:p"):
                break
            t2 = _ptext(b2).strip()
            if t2:
                concl = t2
                break
        if not concl:
            bad.append(f"{cur} 表后缺结论段")
            continue
        if "分别为" not in concl:
            bad.append(f"{cur} 结论段缺「分别为…」数值句")
        hit = [w for w in CONCL_BANNED if w in concl]
        if hit:
            bad.append(f"{cur} 结论段出现判词「{hit[0]}」（纯事实句不得写判词/建议）")
        # 「均」只在同档时允许
        trs = re.findall(r"<w:tr[ >].*?</w:tr>", b, flags=re.S)
        evals = None
        for tr in trs:
            cells = re.findall(r"<w:tc>.*?</w:tc>", tr, flags=re.S)
            if cells and "评价结果" in norm(re.sub(r"<[^>]+>", "", cells[0])):
                evals = [norm(re.sub(r"<[^>]+>", "", c)) for c in cells[1:]]
                break
        if evals and len(set(evals)) > 1 and "均" in concl and re.search(r"均(高于|低于)", concl):
            bad.append(f"{cur} 评价结果逐年不同（{'/'.join(evals)}），结论段不得用「均」")
        cur = None
    if bad:
        return False, "；".join(bad[:4]) + (f"（共 {len(bad)} 处）" if len(bad) > 4 else "")
    return True, ""


STD_SYMBOLS = {
    # 5.3.x → (标准符号 [须出现], 旧符号 [不得出现])
    # 标准原文：DB37/T 2672/2673-2019 §6.2 Ejfgn、§6.3 Ejngn、§6.4 Er、§6.5 Ejd
    "5.3.1": ("Ejfgn", ("Ejrcn", "jrcn")),
    "5.3.2": ("Ejd", ("Eja",)),
    "5.3.3": ("Er", ()),
    "5.3.5": ("Ejngn", ("Egnm",)),
}


def ch5_std_symbol_ok(doc_xml: str, heading_ids=None):
    """5.3 各节公式符号须与标准原文一致（2026-10-16 新增，P1 只告警）。

    背景：包内长期沿用 Ejrcn / Eja / Egnm，且 `chapter5-templates.md` 还把标准在用的
    Ejd/ED 误标为"旧符号已废弃"。实测标准原文（DB37/T 2672/2673-2019 §6）为
    Ejfgn / Ejngn / Er / Ejd，莘县样板也是 jfgn 一脉；Ejrcn/Eja 来自省直参考报告正文。
    检查：① 5.3.x 各节（含公式 OMML 内文本）须出现标准符号；
          ② 不得出现旧符号；③ 式中各项须用标准措辞「单位为…」。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    subs, cur = {}, None
    for b in region:
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        is_head = heading_ids is None or _pstyle(b) in heading_ids
        m = re.match(r"^(5\.3\.\d+)", t) if is_head else None
        if m:
            cur = m.group(1)
            subs[cur] = []
            continue
        if cur:
            # 公式符号在 OMML 的 m:t 里，必须一起取
            subs[cur].append(_ptext(b) + "".join(re.findall(r"<m:t[^>]*>([^<]*)</m:t>", b)))
    bad = []
    for sec, (must, ban) in STD_SYMBOLS.items():
        txt = "".join(subs.get(sec) or [])
        if not txt:
            continue
        if must not in txt:
            bad.append(f"{sec} 未用标准符号 {must}")
        hit = [b for b in ban if b in txt]
        if hit:
            bad.append(f"{sec} 出现旧符号 {hit[0]}（标准为 {must}）")
        if sec in ("5.3.1", "5.3.2", "5.3.3", "5.3.5") and txt.count("单位为") < 2:
            bad.append(f"{sec} 式中措辞未按标准（应写「单位为…，单位」）")
    if bad:
        return False, "；".join(bad[:4])
    return True, ""


def ch5_525_fee_ok(doc_xml: str, heading_ids=None):
    """5.2 费用节（能源资源费用分析）五要素（2026-10-16 新增，P1 只告警）。

    背景：费用节此前是**唯一无断言覆盖**的小节——实测岚山成品缺"整体定性句"、逐年句少一年
    且无增减率、段末没有引图句（三张饼图正文一次都没引用），却能一路绿灯交付。
    本检查按 `chapter5-spec.md`《费用结论段（固定句式）》的五要素逐条核：
      ① 引表句：「…能源费用主要包括…各项能源费用统计见表5.1」，且引语统一；
      ② 整体定性句：含四档词之一（与段2 同一套）；
    ③ 逐年句：`…能源费用较YYYY年…率/幅为X%`，且**条数 ≥ 表5.1 年数 − 1**；
      ④ 段末引图句：`…能源费用占比如图5.X所示`，且该图号在小节内有对应图注；
      ⑤ 括号承载统计数值 → 由 `num_style` 管（见 NUM_STYLE_BANS）。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    # 收集 5.2.5 小节（标题含"费用"）的正文段 + 表5.1 数据行数
    paras, rows_minus_header, cur = [], None, False
    for i, b in enumerate(region):
        if b.startswith("<w:p"):
            t = norm(_ptext(b))
            is_head = heading_ids is None or _pstyle(b) in heading_ids
            if is_head and re.match(r"^5\.2\.\d", t):
                cur = bool(re.match(r"^5\.2\.\d", t)) and "费用" in t
                continue
            if cur and t:
                paras.append(_ptext(b))
        elif b.startswith("<w:tbl") and cur:
            tr = re.findall(r"<w:tr[ >].*?</w:tr>", b, flags=re.S)
            if tr and re.search(r"电费", tr[0]):
                rows_minus_header = len(tr) - 1
    if not paras:
        return True, ""                      # 无费用节（费用全空项目）→ 不检查
    text = "".join(paras)
    miss = []
    # ① 引表句 + 引语统一
    if "能源费用主要包括" not in text or not re.search(r"各项能源费用统计见表5\.\d", text):
        miss.append("缺引表句（应为「…能源费用主要包括…，X1年-X3年各项能源费用统计见表5.1」）")
    if "根据所提供能耗账单及缴费发票统计分析" not in text:
        miss.append("引语未统一（应为「根据所提供能耗账单及缴费发票统计分析」）")
    # ② 整体定性句
    if not any(w in text for w in FEE_TREND_WORDS):
        miss.append("缺整体定性句（四档词之一：" + "/".join(FEE_TREND_WORDS[:4]) + "）")
    # ③ 逐年句条数 + 带增减率
    yearly = re.findall(r"能源费用较\d{4}年[^。；]{0,40}", text)
    if not yearly:
        miss.append("缺逐年句（「…能源费用较{上年}年增加/下降X万元，增减率为X%」）")
    else:
        # 「增长率为X%」与「降幅为X%」都要认（实测写作层两种写法混用；只认"率为"会误报）
        no_rate = [s for s in yearly if not re.search(r"(?:率|幅)为[\d.]+%", s)]
        if no_rate:
            miss.append(f"逐年句缺增减率：{no_rate[0][:24]}…")
        if rows_minus_header and len(yearly) < rows_minus_header - 1:
            miss.append(f"逐年句少写：表5.1 有 {rows_minus_header} 个年度，"
                        f"应写 {rows_minus_header - 1} 句，实际 {len(yearly)} 句")
    # ④ 引图句 + 图号对得上
    m_fig = re.search(r"能源费用占比如图5\.(\d+)所示", text)
    if not m_fig:
        miss.append("缺段末引图句（「…{最新年}年能源费用占比如图5.X所示」）")
    # ⚠️ 只能在**小节段落文本**里找图注：Word 保存会把「图5.10」拆到多个 run，
    #    直接搜原始 XML 会漏（2026-10-16 实测：装配件通过、经 Word 收尾的交付件误报）
    elif not any(re.match(r"^图5\.%s(?:\s|$)" % m_fig.group(1), p.strip()) for p in paras):
        miss.append(f"引图句指到 图5.{m_fig.group(1)}，但报告里没有该图注（饼图与引用对不上）")
    if miss:
        return False, "；".join(miss[:4])
    return True, ""


def ch5_trend_word_ok(doc_xml: str, heading_ids=None):
    """5.2 各能源节段2 的趋势词与逐年率必须对得上（2026-10-16 新增，P1 只告警）。

    口径（用户 2026-10-16 定）：对比值＝**逐年同比变化率里绝对值最大的那个**；
    方向优先（全增=逐年上升、全减=逐年下降），非单调才按 ≤5%/≤10%/≤15%/>15% 分档。
    做法：对每个 5.2.x 节，取总量图注后的第一段（段2），从文里解析"增长率X%／降幅Y%"，
    算出应有的趋势类，再与文中的趋势词比对；两者不一致即告警（防"最大 12% 却写基本稳定"）。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    # 按 H3 切段
    subs, heads, cur = {}, {}, None
    for b in region:
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        is_head = heading_ids is None or _pstyle(b) in heading_ids
        # ⚠️ 只把"标题样式"的段落当作节起点，**正文段落必须照收**——否则逐节扫描会全部跳过、
        #    断言变成静默通过（2026-10-16 实测踩过）
        m = re.match(r"^(5\.2\.\d+)", t) if is_head else None
        if m:
            cur = m.group(1)
            subs[cur] = []
            heads[cur] = t
            continue
        if cur:
            subs[cur].append(_ptext(b))
    bad = []
    for sec, paras in subs.items():
        if not paras or "费用" in heads.get(sec, ""):
            continue                      # 费用节（5.2.5）另有三层口径，本断言不查
        cap = next((i for i, p in enumerate(paras) if re.match(r"^\s*图5\.\d", p.strip())), None)
        if cap is None or cap + 1 >= len(paras):
            continue
        p2 = paras[cap + 1]
        rates = []
        for mm in RATE_RE.finditer(p2):
            sign = 1 if mm.group(1) in _UP_WORDS else -1
            rates.append(sign * float(mm.group(2)))
        if not rates:
            continue
        exp = _trend_expected(rates)
        found = None
        for cls, words in TREND_CLASSES.items():
            if any(w in p2 for w in words):
                found = cls
                break
        if found is None:
            bad.append(f"{sec} 段2 缺趋势词（该写 {exp}，逐年率 "
                       + "、".join(f"{r:+.2f}%" for r in rates) + "）")
        elif found != exp:
            bad.append(f"{sec} 段2 趋势词与最大变化率不符：文中={found}，应={exp}"
                       f"（逐年率 " + "、".join(f"{r:+.2f}%" for r in rates) + "）")
    if bad:
        return False, "；".join(bad[:3]) + (f"（共 {len(bad)} 处）" if len(bad) > 3 else "")
    return True, ""


def ch5_energy_leadin_ok(doc_xml: str, heading_ids=None):
    """5.2 各能源节段1 的引语与单位空格（2026-10-16 新增，P1 只告警）。

    背景：段1 的"逐年数值一句"由写作层写，引语各节不统一——实测岚山 5.2.1 写
    「根据能耗账单及缴费发票统计分析」、5.2.3 写「根据统计数据」，同一章两种说法。
    统一口径（rules.md《3b》与 chapter5-spec 段① 模板）：
      · 引语一律「根据所提供能耗账单及缴费发票统计分析，」；
      · 数值与单位之间空一格（`57207 m³`，不写 `57207m³`）。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    bad_quote, bad_space = [], []
    for b in region:
        if not b.startswith("<w:p"):
            continue
        raw = _ptext(b)                       # 注意：norm() 会删掉全部空白，
        t = norm(raw)                         # 空格类检查必须用原文 raw，否则必误报
        if re.match(r"^5\.2\.\d", t) or not t:
            continue
        if "全年用" in t or "年全年用" in t:                 # 段1 的数值句
            if "根据所提供能耗账单及缴费发票统计分析" not in t:
                bad_quote.append(raw.strip()[:40])
            for m in re.finditer(r"\d\s*(?:kWh|m³|GJ|kg|t)\b", raw):
                if " " not in m.group(0):
                    bad_space.append(m.group(0))
    if bad_quote:
        return False, ("段1 引语未统一（应为「根据所提供能耗账单及缴费发票统计分析」）："
                       + "；".join(bad_quote[:2]))
    if bad_space:
        return False, f"数值与单位之间缺空格：{'、'.join(sorted(set(bad_space))[:3])}"
    return True, ""


def ch5_t51_ok(doc_xml: str):
    """表5.1 形态（2026-10-16 新增，P1 只告警）。

    口径对齐莘县/淄博样板（用户 2026-10-16 定）：
      ① 首列表头＝**斜线表头**——单元格内两段文本 + `w:tl2br` 对角线（装配器由 md 的
         `X\\Y` 形态自动渲染；此前生成器写 `类型\\时间` 却按普通单元格渲染，成品里是一格
         带反斜杠的怪文本）；
      ② 列序固定 电费 / **水费 / 供暖费** / 油费 / 燃气费（样板把水费排在供暖费前）；
      ③ 数值口径：整数不带小数位（此前生成器一律 `:.2f` → `599756.00`）。
    找不到表5.1（费用全空项目）时视为通过。
    """
    for m in re.finditer(r"<w:tbl>.*?</w:tbl>", doc_xml, flags=re.S):
        seg = m.group(0)
        if "电费" not in seg or "合计" not in seg:
            continue
        rows = re.findall(r"<w:tr[ >].*?</w:tr>", seg, flags=re.S)
        if not rows:
            continue
        cells = re.findall(r"<w:tc>.*?</w:tc>", rows[0], flags=re.S)
        labels = [re.sub(r"<[^>]+>", "", c) for c in cells]
        if "w:tl2br" not in cells[0] or len(re.findall(r"<w:p[ >]", cells[0])) < 2:
            return False, ("表5.1 首列表头不是斜线表头（缺 w:tl2br 对角线或两段文本）"
                           "——检查装配器 _diag_header_cell 与 md 里的 `类型\\时间`")
        want = ("电费", "水费", "供暖费", "油费", "燃气费")
        idx = [next((i for i, l in enumerate(labels) if w in l), None) for w in want]
        idx = [i for i in idx if i is not None]
        if idx != sorted(idx):
            return False, f"表5.1 列序不符（应为 电费/水费/供暖费/油费/燃气费）：{labels}"
        body = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", "".join(rows[1:])))
        bad = re.findall(r"\d+\.0+\b", body)
        if bad:
            return False, f"表5.1 出现整数带小数位：{bad[:3]}（应写 {bad[0].split('.')[0]}）"
        return True, ""
    return True, ""


def num_style_ok(doc_xml: str):
    """正文数值与括号规范（2026-10-15 用户定，P1 只告警）。

    背景：用户判定两类写法"非常不规范"——① 「月份（数值）」（岚山用水/用气节实测）；
    ② 设备名后括号塞台数/区域/运行时间（"燃气蒸汽锅炉（2台，供手术室区域，运行时间7:00-18:00）"、
    "分体空调（格力，50台，1.06kW/台）"）。另定数值口径：整数不带小数位、小数两位、禁千分位。

    允许的括号：单位括号（全角）、标准编号括号、图注「（单位：…）」——这三类不匹配上面的形态。
    只扫**叙述段**（表格另由 5.3 表结构断言管，指标值行本就要求两位小数）。
    """
    hits = []
    for t in _narrative_paras(doc_xml):
        if re.match(r"^图5\.\d", t) or re.match(r"^表\d", t):
            continue                      # 图注/表题行："（单位：kWh）"是允许形态
        for label, pat, fix in NUM_STYLE_BANS:
            m = pat.search(t)
            if m:
                s = max(0, m.start() - 16)
                hits.append(f"{label}：「…{t[s:m.end() + 16]}…」→ {fix}")
                break
    if hits:
        return False, "；".join(hits[:3]) + (f"（共 {len(hits)} 处）" if len(hits) > 3 else "")
    return True, ""


def ch5_52_water_ok(doc_xml: str, heading_ids=None):
    """5.2.2 用水节一致性（2026-10-15 新增，P1 只告警）。

    背景：改造前 5.2.2 的段1 用水构成与段4 归因各写各的——岚山实测段1 写「空调、供暖
    系统补水」、段4 只归因「制冷」，同一小节前后自相矛盾；异常说明段也没有能源名闸，
    任何月异常（水/气/热力）都可能被写进用水节。

    检查：
      ① 同源：段1 与段4 提到的补水项必须一致（空调系统补水／供暖系统补水／生活热水系统补水）；
      ② 能源闸：异常说明段（"…用水量同比…主要是…"句）只允许出现在用水节，且句中不得出现
         电/气/热力等他类能源字样；
      ③ 禁系统字眼：平台登记／系统／数据来源（写作层不得把 "平台登记" 写进正文）。
    """
    region = _chapter_region(doc_xml, 5)
    if not region:
        return False, "未定位到 第5章 区间"
    start = end = None
    for i, b in enumerate(region):
        if not b.startswith("<w:p"):
            continue
        t = norm(_ptext(b))
        if heading_ids is not None and _pstyle(b) not in heading_ids:
            continue
        if start is None and re.match(r"^5\.2\.2", t):
            start = i
        elif start is not None and re.match(r"^5\.2\.3", t):
            end = i
            break
    if start is None:
        return True, ""                      # 无 5.2.2（无水项目）→ 不检查
    seg = region[start + 1:(end if end is not None else len(region))]
    paras = [norm(_ptext(b)) for b in seg if b.startswith("<w:p")]
    text = "".join(paras)

    # 补水项 → 段4 的可接受说法（段4 是归因句，不会原样重复"XX系统补水"这四个字：
    # 实测正例「夏季用水量偏高与空调系统冷却塔及管路补水…有关」「供暖季用水量偏高与生活热水系统
    # 用量增加有关」——若做字面全等匹配会把这两句判成"段4 没写"，是误报）
    item_markers = {
        "空调系统补水": ("空调系统", "冷却塔", "管路补水"),
        "供暖系统补水": ("供暖系统", "供暖季"),
        "生活热水系统补水": ("生活热水系统",),
    }
    # 段1 = 含"用水主要为"或"用水系统主要为"的那段；段4 区 = 剩余正文
    lead = next((p for p in paras if "用水主要为" in p or "用水系统主要为" in p), "")
    if not lead:
        return False, "5.2.2 段1 缺少用水构成句（应含「…用水主要为…」）"
    others = "".join(p for p in paras if p is not lead)
    miss = [it for it, marks in item_markers.items()
            if it in lead and not any(m in others for m in marks)]
    if miss:
        return False, ("5.2.2 段1 与段4 的补水项不一致：段1 写了 %s，段4 未出现"
                       "（方案A 要求两处同源）" % "、".join(miss))
    # 异常说明段只允许写水
    for p in paras:
        if re.search(r"用水量同比(?:上升|下降)", p):
            bad = [w for w in ("用电量同比", "用气量同比", "用热量同比", "天然气", "汽油", "柴油")
                   if w in p]
            if bad:
                return False, f"5.2.2 异常说明段串入他类能源：{'、'.join(bad)}"
    for w in ("平台登记", "数据来源"):
        if w in text:
            return False, f"5.2.2 出现系统字眼「{w}」（正文禁止）"
    return True, ""


def building_tables_info(doc_xml: str):
    """建筑基本信息表检测（2026-09-20 新增）：返回各建筑表「首行列数」列表。

    识别：前 3 行内出现「建筑名称/建筑物名称」（兼容「项目 | 内容」旧表头形态）。
    用途：building_tables / building_tables_cols 度量（结构合规性由 V3 负责 P1 检查）。
    """
    cols = []
    for tm in re.finditer(r"<w:tbl[ >].*?</w:tbl>", doc_xml, flags=re.S):
        tbl = tm.group(0)
        rows = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, flags=re.S)[:3]
        if not rows:
            continue
        n_cols = 0
        hit = False
        for k, tr in enumerate(rows):
            tcs = re.findall(r"<w:tc[ >].*?</w:tc>", tr, flags=re.S)
            if not tcs:
                continue
            if k == 0:
                n_cols = len(tcs)
            first = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", tcs[0]))
            if ("建筑名称" in first) or ("建筑物名称" in first):
                hit = True
        if hit:
            cols.append(n_cols)
    return cols


def section_hf_map(z):
    """按 sectPr 顺序返回每节的页眉/页脚部件名（含 sectPr 原文）。

    映射链：w:headerReference / w:footerReference → r:id → word/_rels/document.xml.rels。
    """
    root = etree.fromstring(z.read("word/document.xml"))
    rid_map = {}
    try:
        rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
        for rel in rels:
            rid_map[rel.get("Id")] = rel.get("Target")
    except KeyError:
        pass
    out = []
    for sp in root.findall(".//%ssectPr" % W_NS):
        entry = {"header": [], "footer": [], "xml": etree.tostring(sp, encoding="unicode")}
        for tag, key in (("headerReference", "header"), ("footerReference", "footer")):
            for ref in sp.findall("%s%s" % (W_NS, tag)):
                tgt = (rid_map.get(ref.get(R_NS + "id")) or "").lstrip("/")
                if tgt and not tgt.startswith("word/"):
                    tgt = "word/" + tgt
                if tgt:
                    entry[key].append(tgt)
        out.append(entry)
    return out


def sections_detail(z):
    """按 document 顺序切节，返回 [{orient, text, tables}]。

    tables = [[[cell, ...], ...], ...]（每个表一个行列表）。
    用于核对「附录2 唯一横向节」与「7 列 + 合计行」（2026-09-28 新增）。
    """
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(W_NS + "body")
    out = []
    cur = {"text": [], "tables": []}

    def _close(sect_pr):
        orient = "portrait"
        if sect_pr is not None:
            pg = sect_pr.find(W_NS + "pgSz")
            if pg is not None:
                w = int(pg.get(W_NS + "w") or 0)
                h = int(pg.get(W_NS + "h") or 0)
                if pg.get(W_NS + "orient") == "landscape" or (w and h and w > h):
                    orient = "landscape"
        cur["orient"] = orient
        out.append(dict(cur))

    for child in body:
        tag = child.tag
        if tag == W_NS + "p":
            cur["text"].append("".join(t.text or "" for t in child.iter(W_NS + "t")))
            pr = child.find(W_NS + "pPr")
            if pr is not None and pr.find(W_NS + "sectPr") is not None:
                _close(pr.find(W_NS + "sectPr"))
                cur = {"text": [], "tables": []}
        elif tag == W_NS + "tbl":
            rows = []
            for tr in child.findall(W_NS + "tr"):
                rows.append(["".join(t.text or "" for t in tc.iter(W_NS + "t"))
                             for tc in tr.findall(W_NS + "tc")])
            cur["tables"].append(rows)
    _close(body.find(W_NS + "sectPr"))
    return out


# 2026-10-08：单位括号统一全角；比对时做括号归一，半角/全角都认（向后兼容旧稿）
APX2_HEAD_COLS = ["月份", "水量（m³）", "水费（元）", "水单价（元/m³）",
                  "电量（kWh）", "电费（元）", "电单价（元/kWh）"]


def _norm_paren(s: str) -> str:
    return (s or "").replace("(", "（").replace(")", "）").strip()

# 正文禁忌（2026-09-28）：不得出现 snake_case 形态的英文字段名与 markdown 反引号。
# 只看小写+下划线（如 water_saving_fixture_replacement），避免误伤设备型号/编号
# （YSEZEZS45CKE/22、GB/T 29149-2012）与附件名（report_2024）。
_FIELDNAME_RE = re.compile(r"[a-z]{4,}_[a-z]{3,}")


def _apx2_section(sect_detail):
    """返回附录2 所在节（判定口径：该节文本含「附录2：…」且不含其它「附录N：」标题）。"""
    for sec in sect_detail:
        text = "\n".join(sec["text"])
        if "附录2：" in text and not any(
                f"附录{n}：" in text for n in ("1", "3", "4", "5", "6", "7")):
            return sec
    return None


def _apx2_landscape_ok(sect_detail) -> bool:
    """唯一横向节 = 附录2 节（其它节必须纵向）。"""
    land = [s for s in sect_detail if s.get("orient") == "landscape"]
    if len(land) != 1:
        return False
    apx2 = _apx2_section(sect_detail)
    return apx2 is not None and apx2.get("orient") == "landscape"


_APX_NUM_RE = re.compile(r"^附录\s*\d+\s*[:：]")
_APX2_RE = re.compile(r"^附录\s*2\s*[:：]")


def _chapter_pagebreak_ok(doc_xml: str) -> tuple[bool, str]:
    """大章节另起一页（2026-09-29 用户定）：H1（第1~8章、「附录：」总页）与附录区段的
    「附录N：」H2 **必须带 `<w:pageBreakBefore/>`**（段落属性，不用手工分页符）。

    同时防"重复分页造成空白页"：**附录2** 已由横向分节符另起一页，**不得**再设分页。
    """
    missing: list[str] = []
    dup: list[str] = []
    prev_sect = False      # 上一段是否带 w:sectPr（= 分节符 → 本段位于新页之首）
    for m in re.finditer(r"<w:p[ >].*?</w:p>", doc_xml, re.S):
        seg = m.group(0)
        st = re.search(r'<w:pStyle w:val="([^"]+)"', seg)
        sect_here = "<w:sectPr" in seg
        if not st:
            prev_sect = sect_here
            continue
        style = st.group(1)
        text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", seg)).strip()
        has_brk = "pageBreakBefore" in seg
        if style == "Heading1":
            if not has_brk:
                missing.append(text[:24] or "(H1 空标题)")
        elif style == "Heading2" and _APX_NUM_RE.match(text):
            if _APX2_RE.match(text):
                if has_brk:
                    dup.append(text[:24])
            elif not has_brk and not prev_sect:
                # 紧跟分节符（新页）的附录标题无需再设 pageBreakBefore —— 分节符本身即另起一页，
                # 重复设反而可能多出空白页（实测：附录3 由"切回纵向"的分节符另起一页）。
                missing.append(text[:24])
        prev_sect = sect_here
    why = []
    if missing:
        why.append(f"未设分页 {len(missing)} 处：{'、'.join(missing[:4])}")
    if dup:
        why.append(f"附录2 重复设分页（会多空白页）：{'、'.join(dup[:2])}")
    return (not missing and not dup), "；".join(why)


def _apx2_table_ok(sect_detail) -> bool:
    """附录2 节内每张**逐月表**（表头首列=月份）：7 列固定列序（允许追加 1 列天然气）+ 合计行。

    附录2 内还可能有"三年能源资源消耗及费用汇总表"（表头首列=项目、列为年份），
    该表不受 7 列约束，只要列数 ≥3 即可。
    """
    apx2 = _apx2_section(sect_detail)
    if apx2 is None or not apx2["tables"]:
        return False
    monthly = 0
    for rows in apx2["tables"]:
        head = [c.strip() for c in (rows[0] if rows else [])]
        if not head:
            return False
        if head[0] != "月份":                 # 汇总表等：不套 7 列口径
            if len(head) < 3:
                return False
            continue
        monthly += 1
        if len(head) not in (7, 8):
            return False
        for want, got in zip(APX2_HEAD_COLS, head):
            if _norm_paren(want) != _norm_paren(got):
                return False
        if not any(r and r[0].strip() == "合计" for r in rows):
            return False
    return monthly > 0


def run(docx: str, pdf: str = None, family: str = "auto"):
    if family == "auto":
        family = detect_family(docx)
    z = zipfile.ZipFile(docx)
    znames = z.namelist()
    doc = z.read("word/document.xml").decode("utf-8", "ignore")
    settings = z.read("word/settings.xml").decode("utf-8", "ignore") if "word/settings.xml" in znames else ""
    headers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/header\d+\.xml", n)}
    footers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/footer\d+\.xml", n)}
    media = [n for n in znames if n.startswith("word/media/") and n.lower().endswith(IMG_EXT)]
    sec_maps = section_hf_map(z)
    sect_detail = sections_detail(z)

    instrs = re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", doc)
    text = visible_text(doc)
    tn = norm(text)
    cover_text = text.split("能源审计机构信息表", 1)[0]
    cover_date_ok = bool(re.search(r"20\d{2}年\d{1,2}月", cover_text))
    ch5_n = ch5_narrative_count(doc)
    c531_ok, c531_why = ch5_531_leadin_ok(doc)
    c222_ok, c222_why = ch2_22_structure_ok(doc)
    c222p_ok, c222p_why = ch2_22_photos_ok(doc)
    c3p_ok, c3p_why = ch3_photos_ok(doc)
    c4p_ok, c4p_why = ch4_photos_ok(doc)
    c5f_ok, c5f_why = ch5_figures_ok(doc)
    c4_ok, c4_why = ch4_structure_ok(doc, _heading_style_ids(z))
    c52_ok, c52_why = ch5_52_layout_ok(doc, _heading_style_ids(z))
    c52m_ok, c52m_why = ch5_52_monthly_ok(doc, _heading_style_ids(z))
    c52w_ok, c52w_why = ch5_52_water_ok(doc, _heading_style_ids(z))
    numok, num_why = num_style_ok(doc)
    t51ok, t51_why = ch5_t51_ok(doc)
    leadok, lead_why = ch5_energy_leadin_ok(doc, _heading_style_ids(z))
    trendok, trend_why = ch5_trend_word_ok(doc, _heading_style_ids(z))
    feeok, fee_why = ch5_525_fee_ok(doc, _heading_style_ids(z))
    symok, sym_why = ch5_std_symbol_ok(doc, _heading_style_ids(z))
    conclok, concl_why = ch5_53_conclusion_ok(doc, _heading_style_ids(z))
    n532ok, n532_why = ch5_532_note_ok(doc, _heading_style_ids(z))
    remok, rem_why = ch5_53_removal_ok(doc, _heading_style_ids(z))
    pplok, ppl_why = ch5_533_people_ok(doc, _heading_style_ids(z))
    w534ok, w534_why = ch5_534_water_ok(doc, _heading_style_ids(z))
    bldg_cols = building_tables_info(doc)
    i = tn.find("目录")
    self_ref = False
    if i >= 0:
        # 剔除未缓存占位的"（打开文档…）"文本（R7 形态带前置"目录"，构建器形态
        # "目录"在括号内）；仅当剔除后仍出现"目录"时才判为自收录（历史 bug 形态）。
        seg = re.sub(r"(目录)?（打开文档[^）]*）", "", tn[i + 2:i + 900])
        j = seg.find("目录")
        if j >= 0:
            self_ref = True
    toc_state = "placeholder" if "（打开文档" in tn else "cached"
    pre_map = sec_maps[0] if sec_maps else {"header": [], "footer": [], "xml": ""}
    # 2026-09-28：附录2 另有横向/纵向节，正文节固定为第 2 节，不再是「最后一节」
    body_map = sec_maps[1] if len(sec_maps) > 1 else {"header": [], "footer": [], "xml": ""}
    pre_hdr = "".join(headers.get(n, "") for n in pre_map["header"])
    body_hdr = "".join(headers.get(n, "") for n in body_map["header"])
    body_ftr = "".join(footers.get(n, "") for n in body_map["footer"])

    checks = {
        "zip_ok": True,
        "toc_field": any("TOC" in s for s in instrs),
        "update_fields": "updateFields" in settings,
        "header_watermark": ("EAWatermark" in pre_hdr) and ("EAWatermark" in body_hdr),
        "header_divider": ("w:pBdr" in body_hdr and "w:bottom" in body_hdr) and ("pBdr" not in pre_hdr),
        "footer_page": "PAGE" in body_ftr,
        "footer_plain": ("PAGE" in body_ftr) and ("—" not in body_ftr),
        "header_no_vml": not any("v:textpath" in h for h in headers.values()),
        "section_split": len(sec_maps) >= 2,
        "prebody_clean": (not pre_map["footer"]) and ("能源审计报告" not in pre_hdr) and ("pBdr" not in pre_hdr),
        "cover_date_present": cover_date_ok,
        "body_numbering": ("w:pgNumType" in body_map["xml"]) and ("w:start=\"1\"" in body_map["xml"]),
        "toc_no_self_ref": not self_ref,
        "no_flat_formula": not [p for p in FLAT_FORMULAS if p in text],
        "no_writer_markers": not [m for m in MARKERS if m in text],
        "ch5_narrative": ch5_n >= 15,
        # 5.3.1 表格前结构（定义段/式中/引表句/注唯一）——P1，不阻断
        "ch5_531_leadin": c531_ok,
        # 2.2 三段式结构（逐栋段含建筑面积 + 表数/表号）——P1，不阻断
        "ch2_22_structure": c222_ok,
        # 2.2 图区一致性（图注数 = 图片数、编号连续）——P1，不阻断
        "ch2_22_photos": c222p_ok,
        # 第3章图区一致性（图注数 = 图片数、编号连续）——P1，不阻断
        "ch3_photos": c3p_ok,
        # 第4章计量器具照片（至少 1 注、每注至少 1 图、编号连续）——P1，不阻断
        "ch4_photos": c4p_ok,
        # 第5章图表硬一致性（每注恰一图、编号连续）——阻断
        "ch5_figures": c5f_ok,
        # 第4章小节结构（4.1/4.2/4.3 三节、无 4.4）——P1，不阻断
        "ch4_structure": c4_ok,
        # 5.2 版面（设备列举 + 图注不相邻 + 图注后接分析句）——P1，不阻断
        "ch5_52_layout": c52_ok,
        # 5.2.1 逐月段归因（月份首句须配原因句）——P1，不阻断
        "ch5_52_monthly": c52m_ok,
        # 5.2.2 用水节一致性（段1/段4 同源 + 异常段只含水 + 禁系统字眼）——P1，不阻断
        "ch5_52_water": c52w_ok,
        # 正文数值与括号规范（禁月份括号数值 / 禁设备括号参数 / 整数不带小数位 / 禁千分位）——P1，不阻断
        "num_style": numok,
        # 表5.1 形态（斜线表头 + 列序 + 数值口径）——P1，不阻断
        "ch5_t51": t51ok,
        # 5.2 各能源节段1 引语与单位空格——P1，不阻断
        "ch5_energy_leadin": leadok,
        # 5.2 各能源节段2 趋势词与最大年变化率一致——P1，不阻断
        "ch5_trend_word": trendok,
        # 5.2 费用节五要素（引表句/定性句/逐年句/引图句）——P1，不阻断
        "ch5_525_fee": feeok,
        # 5.3 各节符号与标准一致（Ejfgn/Ejd/Er/Ejngn；禁旧符号）——P1，不阻断
        "ch5_std_symbol": symok,
        # 5.3 各指标表后结论段＝纯事实句（禁判词/建议；跨档不得用「均」）——P1，不阻断
        "ch5_53_conclusion": conclok,
        # 5.3.2 标准注（仅医疗；位置须在「式中」之后）——P1，不阻断
        "ch5_532_note": n532ok,
        # 5.3 剔除项（两表面积同源 + 表格不出现扣减行）——P1，不阻断
        "ch5_53_removal": remok,
        # 5.3.3 用能人数说明（标准句 + 平均用能人数 + 禁四要素括号）——P1，不阻断
        "ch5_533_people": pplok,
        # 5.3.4 用水表（床·日行 + 年用水总量 + L/（床·日））——P1，不阻断
        "ch5_534_water": w534ok,
        "apx2_landscape": _apx2_landscape_ok(sect_detail),
        "apx2_table": _apx2_table_ok(sect_detail),
        "no_field_names": not _FIELDNAME_RE.findall(text) and "`" not in text,
        # 大章节/附录另起一页（2026-09-29 用户定）：见 _chapter_pagebreak_ok
        "chapter_new_page": _chapter_pagebreak_ok(doc)[0],
        # 2026-09-29 用户定：正文引语一律中文全角引号；ASCII 直引号判不合格
        "cn_quotes": '"' not in text,
    }
    details = {}
    flat = [p for p in FLAT_FORMULAS if p in text]
    marks = [m for m in MARKERS if m in text]
    if flat:
        details["no_flat_formula"] = flat
    if marks:
        details["no_writer_markers"] = marks
    if ch5_n < 15:
        details["ch5_narrative"] = "第5章叙述段仅 %d 段（需 ≥ 15）" % ch5_n
    if not checks["section_split"]:
        details["section_split"] = "sectPr 数=%d（期望 ≥2：前置/正文）" % len(sec_maps)
    if not checks["apx2_landscape"]:
        land = [i + 1 for i, s in enumerate(sect_detail) if s.get("orient") == "landscape"]
        details["apx2_landscape"] = (
            "横向节=%s（期望恰好 1 个且为附录2）；附录2 节定位=%s"
            % (land or "无", "命中" if _apx2_section(sect_detail) else "未命中"))
    if not checks["apx2_table"]:
        apx2 = _apx2_section(sect_detail)
        if apx2 is None:
            details["apx2_table"] = "未定位到附录2 节"
        else:
            details["apx2_table"] = "附录2 表头/合计行不符（需 7 列固定列序 + 合计行）；实测表头=%s" % (
                [c.strip() for c in (apx2["tables"][0][0] if apx2["tables"] else [])],)
    if not checks["no_field_names"]:
        details["no_field_names"] = (
            "正文出现英文字段名或反引号：%s（数据来源只留在审核记录/data_sources，"
            "正文改写成中文事实）" % (_FIELDNAME_RE.findall(text)[:5],))
    if not checks["cn_quotes"]:
        n_ascii = text.count('"')
        details["cn_quotes"] = (
            "正文含 %d 个 ASCII 直引号（应为 0）；引语一律用中文全角引号“”"
            "（见 report-format-spec.md《正文禁忌》，2026-09-29 用户定）" % n_ascii)
    if not checks["chapter_new_page"]:
        details["chapter_new_page"] = _chapter_pagebreak_ok(doc)[1]
    if not c531_ok:
        details["ch5_531_leadin"] = c531_why
    if not c222_ok:
        details["ch2_22_structure"] = c222_why
    if not c222p_ok:
        details["ch2_22_photos"] = c222p_why
    if not c3p_ok:
        details["ch3_photos"] = c3p_why
    if not c4p_ok:
        details["ch4_photos"] = c4p_why
    if not c5f_ok:
        details["ch5_figures"] = c5f_why
    if not c4_ok:
        details["ch4_structure"] = c4_why
    if not c52_ok:
        details["ch5_52_layout"] = c52_why
    if not c52m_ok:
        details["ch5_52_monthly"] = c52m_why
    if not c52w_ok:
        details["ch5_52_water"] = c52w_why
    if not numok:
        details["num_style"] = num_why
    if not t51ok:
        details["ch5_t51"] = t51_why
    if not leadok:
        details["ch5_energy_leadin"] = lead_why
    if not trendok:
        details["ch5_trend_word"] = trend_why
    if not feeok:
        details["ch5_525_fee"] = fee_why
    if not symok:
        details["ch5_std_symbol"] = sym_why
    if not conclok:
        details["ch5_53_conclusion"] = concl_why
    if not n532ok:
        details["ch5_532_note"] = n532_why
    if not remok:
        details["ch5_53_removal"] = rem_why
    if not pplok:
        details["ch5_533_people"] = ppl_why
    if not w534ok:
        details["ch5_534_water"] = w534_why
    if not checks["prebody_clean"]:
        why = []
        if pre_map["footer"]:
            why.append("前置节含页脚引用 %s" % pre_map["footer"])
        if "能源审计报告" in pre_hdr:
            why.append("前置节页眉含文字")
        if "pBdr" in pre_hdr:
            why.append("前置节页眉含边框")
        details["prebody_clean"] = "；".join(why) or "未知"
    if not checks["body_numbering"]:
        details["body_numbering"] = "正文节缺 w:pgNumType start=1"
    if not checks["cover_date_present"]:
        details["cover_date_present"] = "封面落款缺“YYYY年M月”报告日期"
    if not checks["footer_plain"]:
        details["footer_plain"] = "正文节页脚含破折号或缺失 PAGE 域"

    if family == "public_building":
        for key in PUBLIC_BUILDING_SKIP:
            checks[key] = True
            details.pop(key, None)
        pb_checks, pb_details = public_building_checks(text)
        checks.update(pb_checks)
        details.update(pb_details)

    metrics = {
        "toc_state": toc_state,
        "oMath": len(re.findall(r"<m:oMath(?![A-Za-z])", doc)),
        "captions": count_captions(doc),
        "tables": len(re.findall(r"<w:tbl[ >]", doc)),
        "ch5_body_paras": ch5_n,
        "building_tables": len(bldg_cols),
        "building_tables_cols": ",".join(str(c) for c in bldg_cols) or "-",
        "drawings": len(re.findall(r"<w:drawing[ >]", doc)),
        "media_files": len(media),
    }
    if pdf:
        import fitz
        d = fitz.open(pdf)
        n = d.page_count
        metrics["pages"] = n

        def _bottom_digit(page):
            """页脚带（底部 66pt）唯一行且为纯数字 → 页码；否则 None。"""
            h = page.rect.height
            lines = []
            for b in page.get_text("dict").get("blocks", []):
                for l in b.get("lines", []):
                    txt = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                    if txt:
                        lines.append((l["bbox"][3], txt))
            cand = [(y1, tx) for y1, tx in lines if y1 >= h - 66]
            if len(cand) == 1 and re.fullmatch(r"\d+", cand[0][1]):
                return int(cand[0][1])
            return None

        def _top_has_header(page):
            band = "".join(w[4] for w in page.get_text("words") if w[1] < 60)
            return "能源审计报告" in re.sub(r"\s+", "", band)

        nums = [_bottom_digit(d[j]) for j in range(n)]
        tops = [_top_has_header(d[j]) for j in range(n)]
        first = next((j for j in range(n) if nums[j] == 1), None)
        if first is None:
            checks["pdf_footer_from_1"] = False
            details["pdf_footer_from_1"] = "未找到页脚为「1」的正文首页（页码从 1 未生效？）"
            metrics["prebody_pages"] = "-"
            metrics["header_pages"] = "-"
            metrics["footer_pages"] = "-"
        else:
            metrics["prebody_pages"] = first
            pre_bad = []
            for j in range(first):
                if tops[j]:
                    pre_bad.append("p%d 顶部带页眉文字" % (j + 1))
                if nums[j] is not None:
                    pre_bad.append("p%d 含页脚数字 %s" % (j + 1, nums[j]))
            checks["pdf_prebody_clean"] = not pre_bad
            if pre_bad:
                details["pdf_prebody_clean"] = "；".join(pre_bad[:6])
            body_pages = n - first
            hf = sum(1 for j in range(first, n) if tops[j])
            ff = sum(1 for j in range(first, n) if nums[j] == j - first + 1)
            metrics["header_pages"] = "%d/%d" % (hf, body_pages)
            metrics["footer_pages"] = "%d/%d" % (ff, body_pages)
            checks["pdf_footer_seq"] = (ff == body_pages)
            if ff != body_pages:
                bad = [("p%d" % (j + 1), nums[j]) for j in range(first, n)
                       if nums[j] != j - first + 1][:6]
                details["pdf_footer_seq"] = "断点: %s" % bad
    return checks, metrics, details


def main() -> int:
    try:                                   # 详情里可能含 m³ 等非 GBK 字符，避免打印崩掉掩盖结果
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="能源审计报告交付断言器")
    ap.add_argument("docx")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--expect", action="append", default=[], help="k=v，可重复；pages 容差 ±2")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--family", choices=["auto", "public_institution", "public_building"],
                    default="auto", help="报告族；auto 从 data.json 推断")
    args = ap.parse_args()

    try:
        checks, metrics, details = run(args.docx, args.pdf, args.family)
    except Exception as exc:  # 解包失败等
        print("[FAIL] zip_ok — %s" % exc)
        if args.json_out:
            json.dump({"docx": args.docx, "passed": False, "error": str(exc)},
                      open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 1

    exp_fail = []
    for e in args.expect:
        k, _, v = e.partition("=")
        k, v = k.strip(), v.strip()
        got = metrics.get(k)
        if got is None:
            exp_fail.append("%s: 无度量值（需要 --pdf？）" % k)
            continue
        try:
            if k == "pages":
                ok = abs(int(got) - int(v)) <= 2
            else:
                ok = int(got) == int(v)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            exp_fail.append("%s: got %s expect %s" % (k, got, v))

    warned = [k for k, v in checks.items() if not v and k in P1_NONBLOCKING]
    failed = [k for k, v in checks.items() if not v and k not in P1_NONBLOCKING] + \
             ["expect:" + f for f in exp_fail]

    for k, v in checks.items():
        tag = "[OK]" if v else ("[WARN]" if k in P1_NONBLOCKING else "[FAIL]")
        d = ""
        if k in details:
            d = " — %s" % details[k]
        print("%s %s%s" % (tag, k, d))
    for f in exp_fail:
        print("[FAIL] expect %s" % f)
    print("-- metrics --")
    for k, v in metrics.items():
        print("  %s = %s" % (k, v))

    if args.json_out:
        json.dump({
            "docx": args.docx, "pdf": args.pdf,
            "checks": checks, "details": details, "metrics": metrics,
            "failed": failed, "passed": not failed,
        }, open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if warned:
        print("[WARN] %d 项 P1 告警（不阻断）：%s" % (len(warned), "、".join(warned)))
    print("[%s] %d 检查失败" % ("PASS" if not failed else "FAIL", len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
