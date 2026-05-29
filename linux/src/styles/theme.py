"""Apple-glass design tokens for Mosslanding."""

from enum import Enum


class ThemeMode(Enum):
    LIGHT = "light"
    DARK = "dark"


class GlassTheme:
    """Central design tokens inspired by Apple's Human Interface Guidelines."""

    FONT_FAMILY = '"SF Pro Display", "Inter", "Noto Sans", system-ui, -apple-system, sans-serif'
    FONT_MONO = '"SF Mono", "JetBrains Mono", "Fira Code", monospace'

    TEXT_XS, TEXT_SM, TEXT_BASE = 10, 12, 13
    TEXT_MD, TEXT_LG, TEXT_XL = 15, 18, 22
    TEXT_2XL, TEXT_3XL = 28, 36

    WEIGHT_LIGHT, WEIGHT_REGULAR, WEIGHT_MEDIUM = 300, 400, 500
    WEIGHT_SEMIBOLD, WEIGHT_BOLD = 600, 700

    SPACE_XS, SPACE_SM, SPACE_MD = 4, 8, 12
    SPACE_BASE, SPACE_LG, SPACE_XL = 16, 20, 24
    SPACE_2XL, SPACE_3XL = 32, 48

    RADIUS_SM, RADIUS_MD, RADIUS_LG = 6, 10, 14
    RADIUS_XL, RADIUS_2XL, RADIUS_FULL = 20, 28, 9999

    SURFACES = {
        "window": {
            "light": {"bg": "rgba(255, 255, 255, 0.55)", "border": "rgba(255, 255, 255, 0.35)", "shadow": "rgba(0, 0, 0, 0.06)"},
            "dark": {"bg": "rgba(28, 28, 30, 0.55)", "border": "rgba(255, 255, 255, 0.08)", "shadow": "rgba(0, 0, 0, 0.30)"},
        },
        "card": {
            "light": {"bg": "rgba(255, 255, 255, 0.72)", "border": "rgba(255, 255, 255, 0.50)", "shadow": "rgba(0, 0, 0, 0.08)"},
            "dark": {"bg": "rgba(44, 44, 46, 0.72)", "border": "rgba(255, 255, 255, 0.10)", "shadow": "rgba(0, 0, 0, 0.40)"},
        },
        "input": {
            "light": {"bg": "rgba(255, 255, 255, 0.85)", "border": "rgba(0, 0, 0, 0.12)", "shadow": "rgba(0, 0, 0, 0.03)"},
            "dark": {"bg": "rgba(60, 60, 67, 0.85)", "border": "rgba(255, 255, 255, 0.12)", "shadow": "rgba(0, 0, 0, 0.20)"},
        },
        "toolbar": {
            "light": {"bg": "rgba(255, 255, 255, 0.35)", "border": "rgba(255, 255, 255, 0.20)", "shadow": "rgba(0, 0, 0, 0.04)"},
            "dark": {"bg": "rgba(28, 28, 30, 0.35)", "border": "rgba(255, 255, 255, 0.05)", "shadow": "rgba(0, 0, 0, 0.20)"},
        },
        "button": {
            "light": {"bg": "rgba(255, 255, 255, 0.78)", "border": "rgba(0, 0, 0, 0.10)", "shadow": "rgba(0, 0, 0, 0.04)"},
            "dark": {"bg": "rgba(60, 60, 67, 0.78)", "border": "rgba(255, 255, 255, 0.08)", "shadow": "rgba(0, 0, 0, 0.20)"},
        },
    }

    ACCENT = "#0f766e"
    ACCENT_HOVER = "#0d9488"
    ACCENT_PRESSED = "#0f766e"
    ACCENT_BG = "rgba(15, 118, 110, 0.10)"
    DANGER = "#dc2626"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"

    INK_PRIMARY_LIGHT = "rgba(0, 0, 0, 0.88)"
    INK_SECONDARY_LIGHT = "rgba(0, 0, 0, 0.60)"
    INK_TERTIARY_LIGHT = "rgba(0, 0, 0, 0.35)"
    INK_PRIMARY_DARK = "rgba(255, 255, 255, 0.90)"
    INK_SECONDARY_DARK = "rgba(255, 255, 255, 0.60)"
    INK_TERTIARY_DARK = "rgba(255, 255, 255, 0.35)"

    DURATION_FAST, DURATION_BASE, DURATION_SLOW = 120, 200, 320

    @classmethod
    def surface(cls, name: str, mode: str) -> dict:
        return cls.SURFACES.get(name, cls.SURFACES["card"]).get(mode, cls.SURFACES["card"]["light"])

    @classmethod
    def ink(cls, level: str, mode: str) -> str:
        inks = {
            "primary": cls.INK_PRIMARY_DARK if mode == "dark" else cls.INK_PRIMARY_LIGHT,
            "secondary": cls.INK_SECONDARY_DARK if mode == "dark" else cls.INK_SECONDARY_LIGHT,
            "tertiary": cls.INK_TERTIARY_DARK if mode == "dark" else cls.INK_TERTIARY_LIGHT,
        }
        return inks.get(level, inks["primary"])
