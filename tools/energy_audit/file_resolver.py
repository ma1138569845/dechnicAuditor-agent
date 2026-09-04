"""附件文件解析器：文件 ID 串 → 可访问的本地路径。

ts_institution_energy_saving.management_files / award_certificate 存放的是
逗号分隔的附件组 ID（ts_attachment.group_id），例如
`2084205758180147200,2084205783094312960`。本模块负责：

1. 解析 ID 串 → 去重整数列表；
2. 通过 PG 查 ts_attachment 拿到相对路径 attach_url；
3. 用 file.base_url（config.yaml / EA_FILE_BASE_URL）拼出完整 URL；
4. 图片附件（award_certificate / management_files 中的图片）下载到本地缓存，
   供报告内嵌（author 第3章写作用 os.path.exists 校验本地路径）；
5. 文档附件（management_files 中的 PDF/Word）下载 + 提取文字 + LLM 提炼，
   回填第三章 3.1「机构职责」/ 3.2「目标方针」正文（见 enrich_management_info）。

base_url 未配置时整体跳过，不阻塞报告生成。
"""

import re
from pathlib import Path
from typing import Dict, List

import requests

from tools.energy_audit._paths import PROJECT_ROOT
from tools.energy_audit.db_config import get_file_base_url

# 仅处理可内嵌的图片类型；其他格式（docx/pdf 等）不下载
_IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')

# 制度文件（文档类型）—— 用于文字提取，非图片展示
_DOC_EXT = ('.pdf', '.docx', '.doc', '.txt', '.md', '.xlsx', '.xls')

_FILE_ID_RE = re.compile(r'\d+')


def _cache_dir() -> Path:
    """本地下载缓存根目录：{PROJECT_ROOT}/reports/attachments"""
    d = PROJECT_ROOT / 'reports' / 'attachments'
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_file_ids(file_ids_str: str) -> List[int]:
    """解析逗号分隔的文件 ID 串 → 去重后的整数列表。

    空串 / 非法输入返回 []，不抛异常。
    """
    if not file_ids_str:
        return []
    return sorted({int(m) for m in _FILE_ID_RE.findall(str(file_ids_str))})


def resolve_attachment_urls(file_ids: List[int], base_url: str = None,
                            pg: 'PgDataQuery' = None) -> List[Dict]:
    """按 group_id 查 ts_attachment，把相对路径拼成完整 URL。

    Returns:
        附件元数据列表，每项 {group_id, name, url}；
        base_url 为空或查不到附件时返回 []。
    """
    base_url = (base_url or get_file_base_url()).rstrip('/')
    if not base_url or not file_ids:
        return []

    from tools.energy_audit.pg_query import PgDataQuery

    close = False
    if pg is None:
        pg = PgDataQuery()
        pg.connect()
        close = True
    try:
        rows = pg.get_attachments(file_ids)
    finally:
        if close:
            pg.disconnect()

    by_id = {r['group_id']: r for r in rows}
    result = []
    for fid in file_ids:
        row = by_id.get(fid)
        if not row:
            continue
        url_path = row.get('attach_url') or ''
        if not url_path.startswith(('http://', 'https://')):
            # 两端各去一斜杠、中间补一斜杠，兼容 attach_url 是否带前导斜杠两种格式
            url_path = f"{base_url.rstrip('/')}/{url_path.lstrip('/')}"
        result.append({
            'group_id': fid,
            'name': row.get('attach_initial_name') or row.get('attach_name') or str(fid),
            'url': url_path,
        })
    return result


def download_attachment_images(attachments: List[Dict]) -> List[str]:
    """下载附件图片到本地缓存目录，返回成功下载的本地路径列表。

    仅处理图片类型；非图片 / 下载失败项自动跳过，不影响其他附件。
    """
    if not attachments:
        return []
    dest = _cache_dir()
    paths = []
    for att in attachments:
        url = att.get('url', '')
        name = att.get('name') or str(att.get('group_id', 'file'))
        if not url or not name.lower().endswith(_IMAGE_EXT):
            continue
        target = dest / name
        if target.exists() and target.stat().st_size > 0:
            paths.append(str(target))
            continue
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            target.write_bytes(resp.content)
            paths.append(str(target))
        except Exception as e:  # noqa: BLE001 - 附件下载失败不应中断整体流程
            print(f"[file_resolver] 附件下载失败 {url}: {e}")
    return paths


def enrich_energy_saving_images(proj, base_url: str = None, pg: 'PgDataQuery' = None) -> None:
    """为 proj.energy_saving 每条记录解析管理文件 / 获奖证书附件图片。

    原地更新 EnergySaving.management_file_images / award_certificate_images
    为下载后的本地路径。base_url 未配置时直接返回（不抛异常）。
    """
    if not proj.energy_saving:
        return
    base_url = (base_url or get_file_base_url()).rstrip('/')
    if not base_url:
        return

    # 收集全部去重文件 ID（跨条目、跨字段）
    ids = set()
    for es in proj.energy_saving:
        ids |= set(parse_file_ids(es.management_files))
        ids |= set(parse_file_ids(es.award_certificate))
    if not ids:
        return

    atts = resolve_attachment_urls(sorted(ids), base_url=base_url, pg=pg)
    if not atts:
        return

    # 一次下载，按 group_id 建立映射，再回填到各记录
    id2path = {}
    for att in atts:
        paths = download_attachment_images([att])
        if paths:
            id2path[att['group_id']] = paths[0]

    for es in proj.energy_saving:
        es.management_file_images = [
            id2path[i] for i in parse_file_ids(es.management_files) if i in id2path
        ]
        es.award_certificate_images = [
            id2path[i] for i in parse_file_ids(es.award_certificate) if i in id2path
        ]


def download_attachment_docs(attachments: List[Dict]) -> List[Dict]:
    """下载非图片文档（PDF/Word/文本）到本地缓存，返回 [{group_id, path, name}]。

    仅处理 _DOC_EXT 类型；图片由 download_attachment_images 单独处理。
    """
    if not attachments:
        return []
    dest = _cache_dir()
    docs = []
    for att in attachments:
        url = att.get('url', '')
        name = att.get('name') or str(att.get('group_id', 'file'))
        if not url or not name.lower().endswith(_DOC_EXT):
            continue
        target = dest / name
        if not (target.exists() and target.stat().st_size > 0):
            try:
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                target.write_bytes(resp.content)
            except Exception as e:  # noqa: BLE001
                print(f"[file_resolver] 文档下载失败 {url}: {e}")
                continue
        docs.append({'group_id': att['group_id'], 'path': str(target), 'name': name})
    return docs


def extract_doc_text(path: str) -> str:
    """提取文档文字：PDF→pymupdf，docx/doc→python-docx，txt/md→直接读。"""
    low = str(path).lower()
    try:
        if low.endswith('.pdf'):
            import pymupdf
            doc = pymupdf.open(str(path))
            try:
                return '\n'.join(page.get_text() for page in doc)
            finally:
                doc.close()
        if low.endswith(('.docx', '.doc')):
            import docx
            d = docx.Document(str(path))
            return '\n'.join(p.text for p in d.paragraphs if p.text.strip())
        if low.endswith(('.txt', '.md')):
            with open(str(path), encoding='utf-8', errors='replace') as f:
                return f.read()
        if low.endswith(('.xlsx', '.xls')):
            import openpyxl
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            lines = []
            for ws in wb.worksheets:
                lines.append(f'【sheet: {ws.title}】')
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                    if cells:
                        lines.append(' | '.join(cells))
            wb.close()
            return '\n'.join(lines)
    except Exception as e:  # noqa: BLE001
        print(f"[file_resolver] 文档文字提取失败 {path}: {e}")
    return ''


def enrich_meter_ledger(proj, base_url: str = None, pg: 'PgDataQuery' = None) -> None:
    """计量器具台账附件（ts_institution_energy_meter.ledger_files）：

    下载台账文档 → 提取文字 → 回填 proj.metering.ledger_text，供 author 4.2
    表4.1 台账清单取数。任何一步失败静默跳过，不阻塞采集。
    """
    try:
        ledger_ids = parse_file_ids(getattr(proj.metering, 'ledger_files', ''))
        if not ledger_ids:
            return
        base_url = (base_url or get_file_base_url()).rstrip('/')
        if not base_url:
            return
        atts = resolve_attachment_urls(ledger_ids, base_url=base_url, pg=pg) or []
        docs = download_attachment_docs(atts) or []
        if not docs:
            return
        texts = []
        for d in docs:
            try:
                t = extract_doc_text(d.get('path', ''))
                if t:
                    texts.append(t)
            except Exception:
                continue
        if texts:
            proj.metering.ledger_text = '\n\n'.join(texts)
    except Exception:
        pass


def enrich_management_info(proj, base_url: str = None, pg: 'PgDataQuery' = None) -> None:
    """有能源管理制度（energy_management==1）且有制度文件时：
    下载制度文档 → 提取文字 → LLM 提炼，回填 proj.management。

    - management_org      ← 3.1 机构职责
    - management_policy   ← 3.2 目标与方针（合并为一段）

    任何一步失败/缺 key 都静默跳过，保留报告生成器的兜底文案，不阻塞流程。
    """
    if not proj.energy_saving:
        return
    base_url = (base_url or get_file_base_url()).rstrip('/')
    if not base_url:
        return

    # 取最新一条「有制度」且带制度文件的记录
    target = None
    for es in sorted((e for e in proj.energy_saving if e),
                     key=lambda e: e.statistical_year or 0, reverse=True):
        if es.energy_management == 1:
            target = es
            break
    if not target:
        return

    ids = parse_file_ids(target.management_files)
    if not ids:
        return

    atts = resolve_attachment_urls(ids, base_url=base_url, pg=pg)
    docs = download_attachment_docs(atts)
    if not docs:
        return

    texts = [t for t in (extract_doc_text(d['path']) for d in docs) if t and t.strip()]
    if not texts:
        return

    from tools.energy_audit.llm_client import summarize_management_docs
    unit = (getattr(getattr(proj, 'base', None), 'unit_short', '')
            or getattr(getattr(proj, 'base', None), 'unit_name', ''))
    res = summarize_management_docs(texts, unit)
    if not res:
        return

    if res.get('org'):
        proj.management.management_org = res['org']
    if res.get('goals_policy'):
        proj.management.management_policy = res['goals_policy']
