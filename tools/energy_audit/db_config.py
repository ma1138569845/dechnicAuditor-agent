"""
能源审计 PG 数据库连接配置统一解析器。

解析优先级（高 → 低）：
  1. 显式参数 overrides（调用方传入，空字符串/None 视为未提供）
  2. 环境变量 EA_PG_*（兼容旧命名 DB_*）
  3. Hermes config.yaml → energy_audit.database.*（{HERMES_HOME}/config.yaml）
  4. 包内 config.yaml → database.*（tools/energy_audit/config.yaml，仅存非密默认值）
  5. 内置非密默认值

密码（password）不设内置默认值：以上任一来源提供即可，全部缺失时抛出
RuntimeError 并给出配置指引。切勿在 .py 源码中写入明文密码。

prod - serial number - 5
"""

import os
from pathlib import Path
from typing import Dict, Optional

# 配置键 → (EA_PG_* 环境变量, 旧版 DB_* 环境变量, 内置默认值)
_KEYS = {
    'host':     ('EA_PG_HOST',     'DB_HOST',     '10.10.1.165'),
    'port':     ('EA_PG_PORT',     'DB_PORT',     '5432'),
    'database': ('EA_PG_NAME',     'DB_NAME',     'dc_energy_audit2'),
    'user':     ('EA_PG_USER',     'DB_USER',     'postgres'),
    'password': ('EA_PG_PASSWORD', 'DB_PASSWORD', None),
    'sslmode':  ('EA_PG_SSLMODE',  'DB_SSLMODE',  'prefer'),
}

_LOCAL_CONFIG_YAML = Path(__file__).resolve().parent / 'config.yaml'


def _non_blank(value) -> bool:
    return value is not None and str(value).strip() != ''


def _from_env(key: str) -> Optional[str]:
    ea_var, db_var, _ = _KEYS[key]
    for var in (ea_var, db_var):
        val = os.environ.get(var)
        if _non_blank(val):
            return str(val).strip()
    return None


def _hermes_config_path() -> Optional[Path]:
    """定位 Hermes 全局 config.yaml（不依赖 hermes_cli.webui 包，可独立运行）"""
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home()) / 'config.yaml'
    except Exception:
        pass
    for candidate in (
        Path(os.environ.get('LOCALAPPDATA', '')) / 'hermes' / 'config.yaml',
        Path.home() / '.hermes' / 'config.yaml',
    ):
        if candidate.exists():
            return candidate
    return None


def _from_hermes_config(section: str, key: str) -> Optional[str]:
    """Hermes 全局 config.yaml → energy_audit.{section}.{key}"""
    try:
        path = _hermes_config_path()
        if not path or not path.exists():
            return None
        import yaml
        with open(path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        val = ((cfg.get('energy_audit') or {}).get(section) or {}).get(key)
        if _non_blank(val):
            return str(val).strip()
    except Exception:
        pass
    return None


def _from_local_config(section: str, key: str) -> Optional[str]:
    """包内 config.yaml → {section}.{key}（独立运行、无 Hermes 环境时兜底）"""
    try:
        if not _LOCAL_CONFIG_YAML.exists():
            return None
        import yaml
        with open(_LOCAL_CONFIG_YAML, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        val = (cfg.get(section) or {}).get(key)
        if _non_blank(val):
            return str(val).strip()
    except Exception:
        pass
    return None


def get_pg_config(overrides: Optional[Dict] = None) -> Dict:
    """解析 PG 连接配置，返回 psycopg2.connect 可直接使用的字典。

    Args:
        overrides: 调用方显式配置，非空值拥有最高优先级；
                   传 None 或空 dict 则完全走配置链。

    Raises:
        RuntimeError: 所有来源均未提供 password 时。
    """
    overrides = overrides or {}
    resolved = {}
    for key, (_, _, default) in _KEYS.items():
        val = overrides.get(key)
        if not _non_blank(val):
            val = _from_env(key)
        if not _non_blank(val):
            val = _from_hermes_config('database', key)
        if not _non_blank(val):
            val = _from_local_config('database', key)
        if not _non_blank(val):
            val = default
        if _non_blank(val):
            resolved[key] = str(val).strip()

    if 'password' not in resolved:
        raise RuntimeError(
            'PG 数据库密码未配置。请通过以下任一方式提供：\n'
            '  1. 环境变量 EA_PG_PASSWORD（或 DB_PASSWORD）\n'
            '  2. Hermes config.yaml → energy_audit.database.password\n'
            '  3. tools/energy_audit/config.yaml → database.password（本地开发）'
        )
    return resolved


def _file_value(overrides: Dict, env_var: str, key: str) -> Optional[str]:
    """按 overrides → 环境变量 → Hermes config → 本地 config 顺序取 file 段配置值。"""
    val = overrides.get(key)
    if not _non_blank(val):
        val = os.environ.get(env_var)
    if not _non_blank(val):
        val = _from_hermes_config('file', key)
    if not _non_blank(val):
        val = _from_local_config('file', key)
    return str(val).strip() if _non_blank(val) else None


def _db_host() -> Optional[str]:
    """解析数据库主机（不要求 password），供文件服务地址回退使用。"""
    return (_from_env('host') or _from_hermes_config('database', 'host')
            or _from_local_config('database', 'host') or _KEYS['host'][2])


def get_file_base_url(overrides: Optional[Dict] = None) -> str:
    """解析文件服务基础地址（拼接 ts_attachment.attach_url 相对路径 → 完整 URL）。

    优先级（高 → 低）：
      1. 完整前缀 base_url（overrides → EA_FILE_BASE_URL → Hermes → 本地 config）
      2. base_url 未填时，用 scheme + host + port 拼接；host 留空回退到数据库主机。

    未显式配置 base_url / host / port 任一者时返回空字符串，
    调用方据此跳过附件解析，不阻塞报告生成。
    """
    overrides = overrides or {}

    base_url = _file_value(overrides, 'EA_FILE_BASE_URL', 'base_url')
    if base_url:
        return base_url.rstrip('/')

    explicit_host = _file_value(overrides, 'EA_FILE_HOST', 'host')
    explicit_port = _file_value(overrides, 'EA_FILE_PORT', 'port')
    if not explicit_host and not explicit_port:
        return ''

    scheme = _file_value(overrides, 'EA_FILE_SCHEME', 'scheme') or 'http'
    host = explicit_host or _db_host()
    if not host:
        return ''

    url = f"{scheme}://{host}"
    if explicit_port:
        url += f":{explicit_port}"
    return url.rstrip('/')
