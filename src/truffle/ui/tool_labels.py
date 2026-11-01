"""参数栏的中文显示名（工具名 / 参数名 / 枚举项）。

- 只影响前端展示，不改变发给大模型的 API 名称与取值；
- 未登记的键回退为原始英文名。
"""

from __future__ import annotations

TOOL_LABELS: dict[str, str] = {
    "skin_smooth": "磨皮",
    "whiten": "美白",
    "slim_face": "瘦脸",
    "enlarge_eyes": "大眼",
    "remove_blemish": "祛痘祛斑",
    "color_adjust": "调色",
    "color_temp": "色温色调",
    "hsl": "HSL",
    "curves": "曲线",
    "tone_recovery": "高光阴影",
    "dehaze": "去雾",
    "hdr": "HDR 影调",
    "sharpen_clarity": "锐化清晰度",
    "vignette": "暗角",
    "film": "胶片",
    "rotate_flip": "旋转翻转",
    "teeth_whiten": "牙齿美白",
    "remove_dark_circles": "去黑眼圈",
    "eye_brighten": "眼睛提亮",
    "hair_color": "发色",
    "lipstick": "口红",
    "background_blur": "背景虚化",
    "body_slim": "瘦身瘦腰",
    "leg_lengthen": "长腿",
    "distort": "扭曲",
}

PARAM_LABELS: dict[str, str] = {
    "strength": "强度",
    "threshold": "阈值",
    "brightness": "亮度",
    "contrast": "对比度",
    "saturation": "饱和度",
    "temperature": "色温",
    "tint": "色调",
    "highlights": "高光",
    "shadows": "阴影",
    "sharpen": "锐化",
    "clarity": "清晰度",
    "amount": "强度",
    "softness": "柔和度",
    "grain": "颗粒",
    "fade": "褪色",
    "rotate": "旋转角度",
    "flip": "翻转",
    "feather": "羽化",
    "mode": "方式",
    "center_x": "中心 X",
    "center_y": "中心 Y",
    "radius": "半径",
    "hue": "色相",
    "lightness": "明度",
    "black": "黑场",
    "midtones": "中间调",
    "white": "白场",
    "local_contrast": "局部对比",
    "sclera": "眼白",
}

ENUM_LABELS: dict[object, str] = {
    0: "0°",
    90: "90°",
    180: "180°",
    270: "270°",
    "none": "不翻转",
    "horizontal": "水平镜像",
    "vertical": "垂直镜像",
    "twirl": "旋转",
    "pinch": "收拢",
    "bulge": "膨胀",
    "stretch_h": "横向拉伸",
    "stretch_v": "纵向拉伸",
}


def tool_label(name: str) -> str:
    from .i18n import tr

    return tr(TOOL_LABELS.get(name, name))


def param_label(name: str) -> str:
    from .i18n import tr

    return tr(PARAM_LABELS.get(name, name))


def enum_label(item: object) -> str:
    from .i18n import tr

    return tr(ENUM_LABELS.get(item, str(item)))
