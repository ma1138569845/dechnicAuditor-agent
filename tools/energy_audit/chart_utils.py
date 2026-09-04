"""
matplotlib 图表中文字体与上标渲染 —— 共享工具

所有图表入口（imitate 仿写渲染 / chapter5_agent 等）统一从这里配置字体，
避免各模块各自硬编码 rcParams 导致配置分散、行为不一致。

背景：SimHei 缺少 ²/³/¹（U+00B2/B3/B9）等上标字形，直接渲染会显示为方框并
抛出 "Glyph ... missing from font" 告警。因此：
  1. 字体链优先选用带完整 Latin-1 上标的中文字体（Microsoft YaHei / SimSun /
     DengXian / Noto Sans SC 等），SimHei 仅作最后兜底；
  2. chart_text() 把 ²/³/¹ 转成 matplotlib mathtext（$^2$/$^3$/$^1$），
     上标由数学字体（DejaVu）渲染，机器无关，任何字体环境下都不会缺字形。
"""

# SimHei 缺少 ²/³/¹ 等上标字形，优先用带完整上标的 CJK 字体，SimHei 兜底
CHART_CJK_FONTS = ['Microsoft YaHei', 'SimSun', 'DengXian', 'Noto Sans SC', 'SimHei', 'sans-serif']


def setup_chart_font(plt):
    """统一配置 matplotlib 中文字体链与负号显示。调用前需先 import matplotlib.pyplot as plt。"""
    plt.rcParams['font.sans-serif'] = CHART_CJK_FONTS
    plt.rcParams['axes.unicode_minus'] = False


def chart_text(s) -> str:
    """将 ²/³/¹ 上标转为 matplotlib mathtext（$^2$/$^3$/$^1$），
    使上标用数学字体（DejaVu）渲染，避免中文字体缺字形显示为方框。

    用法：传给 matplotlib 的标题/轴标签/刻度文本都经过此函数，例如
        ax.set_ylabel(chart_text(f'{label}({unit})'))
    """
    if not s:
        return s
    return (s.replace('²', '$^2$')
             .replace('³', '$^3$')
             .replace('¹', '$^1$'))
