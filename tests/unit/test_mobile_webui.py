from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"
STYLESHEET = PROJECT_ROOT / "static" / "css" / "style.css"


def test_mobile_viewport_supports_safe_areas():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'width=device-width, initial-scale=1.0, viewport-fit=cover' in html


def test_phone_layout_has_single_column_and_touch_targets():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "@media (max-width: 600px)" in css
    assert "min-height: 100dvh" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "min-height: 44px" in css

    phone_rules = css.split("@media (max-width: 600px)", 1)[1]
    assert ".situation-grid.grid-2" in phone_rules
    assert ".situation-grid.grid-3" in phone_rules
    assert "grid-template-columns: minmax(0, 1fr)" in phone_rules
    assert ".source-tile-actions" in phone_rules
    assert ".toast" in phone_rules
    assert ".main-container > *" in phone_rules
    assert ".segmented-toggle" in phone_rules
    assert "min-width: 0" in phone_rules
    assert ".header-right" in phone_rules
    assert "grid-template-columns: minmax(0, 1fr)" in phone_rules


def test_mobile_controls_have_keyboard_and_touch_feedback():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "outline: 3px solid var(--accent-primary)" in css
    assert ":active" in css
    assert "transform: scale(0.98)" in css
    assert "@media (hover: none) and (pointer: coarse)" in css


def test_dynamic_feedback_is_announced_to_assistive_technology():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="role-gate" role="dialog" aria-modal="true"' in html
    assert 'id="toast" role="status" aria-live="polite"' in html


def test_reduced_motion_disables_nonessential_animation():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "@media (prefers-reduced-motion: reduce)" in css
    reduced_motion_rules = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "animation: none" in reduced_motion_rules
