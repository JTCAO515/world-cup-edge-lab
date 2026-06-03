from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_top_navigation_has_interactive_view_targets():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert 'data-view="prediction"' in html
    assert 'data-view="backtest"' in html
    assert 'id="predictionView"' in html
    assert 'id="backtestView"' in html


def test_frontend_script_renders_backtest_view():
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "function bindNavigation" in script
    assert "function renderBacktestView" in script
    assert "state.currentView" in script
