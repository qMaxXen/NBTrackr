from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QImage,
    QPainter,
)

_FONT_FAMILY_CACHE = {}
_METRICS_CACHE = {}


def load_qfont(size, custom_font_path="", fallback_family=None):
    family = None
    is_bold = False
    is_italic = False
    if custom_font_path:
        if custom_font_path in _FONT_FAMILY_CACHE:
            family, is_bold, is_italic = _FONT_FAMILY_CACHE[custom_font_path]
        else:
            font_id = QFontDatabase.addApplicationFont(custom_font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    family = families[0]
                    styles = QFontDatabase.styles(family)
                    style_name = styles[0] if styles else ""
                    is_bold = "Bold" in style_name
                    is_italic = "Italic" in style_name or "Oblique" in style_name
                    _FONT_FAMILY_CACHE[custom_font_path] = (family, is_bold, is_italic)
    if family is None:
        family = fallback_family or "Liberation Sans"
        is_bold = True
    font = QFont(family)
    font.setPixelSize(size)
    font.setBold(is_bold)
    font.setItalic(is_italic)
    return font


def metrics_for(font):
    key = (font.family(), font.pixelSize(), font.bold())
    font_metrics = _METRICS_CACHE.get(key)
    if font_metrics is None:
        font_metrics = QFontMetrics(font)
        _METRICS_CACHE[key] = font_metrics
    return font_metrics


def text_width(text, font):
    return metrics_for(font).horizontalAdvance(text)


def text_height(font):
    font_metrics = metrics_for(font)
    return font_metrics.ascent() + font_metrics.descent()


def draw_text(painter, x, y_top, text, font, color):
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.setFont(font)
    painter.setPen(QColor(*color[:3], color[3] if len(color) > 3 else 255))
    font_metrics = metrics_for(font)
    painter.drawText(x, y_top + font_metrics.ascent(), text)


def draw_text_outlined(painter, x, y_top, text, font, fill_color, outline_color, outline_width):
    font_metrics = metrics_for(font)
    baseline_y = y_top + font_metrics.ascent()

    if outline_width <= 0:
        draw_text(painter, x, y_top, text, font, fill_color)
        return

    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.setFont(font)
    painter.setPen(QColor(*outline_color[:3]))
    radius = outline_width
    for delta_x in range(-radius, radius + 1):
        for delta_y in range(-radius, radius + 1):
            if delta_x == 0 and delta_y == 0:
                continue
            if delta_x * delta_x + delta_y * delta_y > radius * radius:
                continue
            painter.drawText(x + delta_x, baseline_y + delta_y, text)
    painter.setPen(QColor(*fill_color[:3], fill_color[3] if len(fill_color) > 3 else 255))
    painter.drawText(x, baseline_y, text)


def fill_rectangle(painter, x0, y0, x1, y1, color):
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.fillRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1, QColor(*color[:3], color[3] if len(color) > 3 else 255))


def new_canvas(w, h, bg_color):
    img = QImage(max(w, 1), max(h, 1), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(*bg_color[:3], bg_color[3] if len(bg_color) > 3 else 255))
    return img


def load_icon(path, size):
    icon = QImage(path)
    if icon.isNull():
        return None
    icon = icon.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    return icon.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def apply_opacity(qimage, op):
    if op >= 1.0:
        return qimage
    result = QImage(qimage.size(), QImage.Format_ARGB32_Premultiplied)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setOpacity(op)
    painter.drawImage(0, 0, qimage)
    painter.end()
    return result
