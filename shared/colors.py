def gradient_color(angle: float):
    if angle <= 90:
        t = angle / 90.0
        red = int(255 * t)
        green = 255
        return (red, green, 0)
    t = (angle - 90) / 90.0
    red = 255
    green = int(255 * (1 - t))
    return (red, green, 0)


def certainty_color(pct: float):
    pct = max(0.0, min(100.0, pct))
    return gradient_color((100 - pct) * 1.8)


def blind_evaluation_color(evaluation):
    colors = {
        "EXCELLENT": (0, 255, 0),
        "HIGHROLL_GOOD": (100, 255, 100),
        "HIGHROLL_OKAY": (114, 214, 2),
        "BAD_BUT_IN_RING": (222, 220, 3),
        "BAD": (255, 100, 0),
        "NOT_IN_RING": (255, 0, 0),
    }
    return colors.get(evaluation, (255, 255, 255))


def hex_to_rgb(hexstr, fallback=(0, 0, 0)):
    try:
        if not isinstance(hexstr, str):
            return fallback
        s = hexstr.strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) != 6:
            return fallback
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except Exception:
        return fallback


def with_alpha(color, alpha_float):
    r, g, b = color[0], color[1], color[2]
    a = max(0, min(255, int(alpha_float * 255)))
    return (r, g, b, a)


def format_blind_evaluation(evaluation):
    evaluations = {
        "EXCELLENT": "excellent",
        "HIGHROLL_GOOD": "good for highroll",
        "HIGHROLL_OKAY": "okay for highroll",
        "BAD_BUT_IN_RING": "bad, but in ring",
        "BAD": "bad",
        "NOT_IN_RING": "not in any ring",
    }
    return evaluations.get(evaluation, evaluation)
