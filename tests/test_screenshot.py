from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

from quote_agent.agents.screenshot import capture_redacted_screenshot

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "widgets.html").resolve().as_uri()


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE_URL)
        yield page
        browser.close()


def _center_pixel(page, selector: str) -> tuple:
    box = page.locator(selector).bounding_box()
    return (int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))


def test_capture_redacted_screenshot_masks_a_sensitive_field(page, tmp_path):
    # "#first-name" resolves via the exact "first name" alias to
    # identity.first_name, a sensitive path -- must be covered by an
    # opaque mask before the screenshot is taken, verified by actually
    # inspecting the saved image's pixels, not by trusting the masking
    # code did what it claims.
    out_path = tmp_path / "evidence.png"
    cx, cy = _center_pixel(page, "#first-name")

    capture_redacted_screenshot(page, out_path)

    assert out_path.exists()
    img = Image.open(out_path)
    assert img.getpixel((cx, cy))[:3] == (0, 0, 0)


def test_capture_redacted_screenshot_leaves_non_sensitive_fields_visible(page, tmp_path):
    # "#winter-tires" resolves via the exact "do you have winter tires"
    # alias to vehicles[].winter_tires, not sensitive -- masking must be
    # targeted, not a blanket black-out of the whole page.
    out_path = tmp_path / "evidence.png"
    cx, cy = _center_pixel(page, "#winter-tires")

    capture_redacted_screenshot(page, out_path)

    img = Image.open(out_path)
    assert img.getpixel((cx, cy))[:3] != (0, 0, 0)


def test_capture_redacted_screenshot_creates_parent_directories(page, tmp_path):
    out_path = tmp_path / "nested" / "dir" / "evidence.png"

    capture_redacted_screenshot(page, out_path)

    assert out_path.exists()
