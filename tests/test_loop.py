from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from quote_agent.agents import CaptchaDetected, discover_fields, fill_visible_fields
from quote_agent.models import (
    Address,
    Consent,
    ConsentMode,
    CoverageConfig,
    Identity,
    InsuranceHistory,
    IntakeProfile,
    Vehicle,
)

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "widgets.html").resolve().as_uri()


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(legal_name="Jane Applicant", date_of_birth="1990-01-01"),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        # NOTE: province stored here as the display label ("Ontario") to match this fixture's
        # <select> options -- a real intake.json more likely stores the code ("ON"). Storing
        # a value that matches the schema but not necessarily the site's own option text is a
        # real, expected friction point once this runs against a genuine live site.
        address=Address(street="123 Main St", city="Toronto", province="Ontario", postal_code="M5V 3A8"),
        vehicles=[
            Vehicle(
                vin="VIN0",
                model_year=2020,
                make="Toyota",
                model="Corolla",
                ownership="owned",
                primary_use="commute",
                annual_km=12000,
                winter_tires=True,
            )
        ],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01", third_party_liability_limit=2_000_000, dcpd_included=True
        ),
    )


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE_URL)
        yield page
        browser.close()


def test_fill_visible_fields_fills_known_aliased_fields_without_llm(page):
    intake = make_intake()

    known_aliased_labels = {"First Name", "Province", "Do you have winter tires?", "Vehicle use"}

    def failing_llm(label: str) -> str | None:
        if label in known_aliased_labels:
            raise AssertionError(f"llm_fallback should not be needed for {label!r}")
        return None  # other fixture fields (e.g. the dangling-label case) may legitimately need it

    report = fill_visible_fields(page, intake, llm_fallback=failing_llm)

    assert page.locator("#first-name").input_value() == "Jane"
    assert page.locator("#province").input_value() == "ON"
    assert page.locator("#winter-tires").is_checked()
    # stored value is "commute", displayed option is "Commuting" -- not a
    # substring match, only works via resolve_display_value's alias table
    assert page.locator('#vehicle-use-group [role="radio"][aria-checked="true"]').inner_text() == "Commuting"

    assert report.filled["First Name"] == "identity.first_name"
    assert report.filled["Province"] == "address.province"
    assert report.filled["Do you have winter tires?"] == "vehicles[].winter_tires"
    assert report.filled["Vehicle use"] == "vehicles[].primary_use"


def test_fill_visible_fields_reports_resolved_but_unfillable_readonly_widget(page):
    # "Start Date" resolves via a known alias, but its widget (a readonly
    # field where a calendar popup, not typing, sets the value) can't be
    # classified as fillable from a single element -- it must be reported,
    # not silently skipped or incorrectly filled as plain text.
    intake = make_intake()
    report = fill_visible_fields(page, intake)

    assert "Start Date" in report.skipped_unknown_widget
    assert page.locator("#start-date").input_value() == ""


def test_fill_visible_fields_types_raw_value_into_autocomplete_field(page):
    # "Street Address" resolves via a known alias and, since autocomplete
    # can no longer be used as an UNKNOWN signal (see detect.py), is
    # treated as plain text: the raw stored value gets typed in directly.
    # For this fixture's simulated widget that doesn't click a suggestion,
    # so the result isn't necessarily a "valid" selected address -- a
    # known, accepted trade-off now that autocomplete="off" has been
    # confirmed unreliable as a distinguishing signal on real sites.
    intake = make_intake()
    report = fill_visible_fields(page, intake)

    assert report.filled["Street Address"] == "address.street"
    assert page.locator("#address").input_value() == "123 Main St"


def test_discover_fields_falls_back_past_a_dangling_for_reference(page):
    # "My alternate address is" has for="postal_code", which matches no
    # element's id at all (mirrors a real site's stale reference to a
    # hidden decoy control). discover_fields must still find the real,
    # visible sibling text field instead of silently dropping the label --
    # and must not itself be fooled into pairing the label with either of
    # the two hidden decoy inputs sitting in between.
    pairs = dict(discover_fields(page))

    assert "My alternate address is" in pairs
    control = pairs["My alternate address is"]
    assert control.get_attribute("id") == "alt-street-address"
    assert control.is_visible()


def test_discover_fields_does_not_guess_a_control_for_a_label_wrapping_several(page):
    # "#dob-group"'s wrapping <label>Date of birth</label> (no for=) wraps
    # three distinct controls, not one -- confirmed on a real site (Aviva).
    # Guessing the first one would both mislabel it and block its own
    # correct, distinct aria-label from ever being discovered.
    pairs = dict(discover_fields(page))

    assert "Date of birth" not in pairs
    assert pairs["Enter the month you were born"].get_attribute("id") == "dob-month"
    assert pairs["Enter the day you were born"].get_attribute("id") == "dob-day"
    assert pairs["Enter the year you were born"].get_attribute("id") == "dob-year"


def test_discover_fields_does_not_fill_a_honeypot_field(page):
    # "#honeypot-input" has a real for= association resolving to a control
    # with its own real layout box, so a naive check on the control alone
    # would pass -- but the <label> itself is display:none, meaning no
    # real user could ever see the field's name. Confirmed on a real site
    # (Aviva) as an anti-bot honeypot; must stay undiscoverable.
    pairs = dict(discover_fields(page))

    assert "Previous Insurance Start Date" not in pairs
    matches = [label for label, control in pairs.items() if control.get_attribute("id") == "honeypot-input"]
    assert matches == []


def test_discover_fields_does_not_guess_among_multiple_dangling_for_candidates(page):
    # "#dangling-for-multiple-candidates-row"'s <label for="dateOfBirth">
    # dangles (no element has that id) and sits alongside THREE real
    # candidates, not one -- confirmed on a real site (Aviva). Unlike the
    # single-candidate mislinked-postal-code case, guessing the first one
    # here both mislabels it and blocks its own correct aria-label from
    # ever being discovered.
    pairs = dict(discover_fields(page))

    assert "Date of birth" not in pairs
    assert pairs["Birth month, dangling-for variant"].get_attribute("id") == "real-dob-month"
    assert pairs["Birth day, dangling-for variant"].get_attribute("id") == "real-dob-day"
    assert pairs["Birth year, dangling-for variant"].get_attribute("id") == "real-dob-year"


def test_discover_fields_does_not_guess_a_control_for_a_decorative_label(page):
    # "Terms of Use and Privacy Policy." has no for= and wraps no control
    # -- unlike the dangling-for= case above, there's no evidence this
    # label was ever meant to point at a specific control, so it must not
    # get guess-paired with the unrelated checkbox sitting next to it.
    pairs = dict(discover_fields(page))

    assert "Terms of Use and Privacy Policy." not in pairs
    assert pairs["I agree to the"].get_attribute("id") == "consent-checkbox"


def test_discover_fields_finds_a_controls_own_aria_label(page):
    # "#company-name" has no <label> at all -- its only identifying text is
    # its own aria-label attribute (confirmed on a real site, Aviva: its
    # actual Year/Make/Model <select> elements are marked up exactly this
    # way). Must be discoverable even with no separate <label> element.
    pairs = dict(discover_fields(page))

    assert "Company name" in pairs
    assert pairs["Company name"].get_attribute("id") == "company-name"


def test_fill_visible_fields_reports_no_data_instead_of_filling_the_literal_string_none(page):
    # "#company-name" resolves fine and classifies as a normal TEXT widget,
    # but the field it maps to (commute_one_way_km) has no value in this
    # intake -- confirmed on a real site (Aviva) that leaving this
    # unguarded fills the literal string "None" into the page, which a
    # type="number" input outright rejects and a plain text field would
    # silently accept as garbage instead.
    intake = make_intake()
    assert intake.vehicles[0].commute_one_way_km is None

    def llm_fallback(label: str) -> str | None:
        return "vehicles[].commute_one_way_km" if label == "Company name" else None

    report = fill_visible_fields(page, intake, llm_fallback=llm_fallback)

    assert report.no_data["Company name"] == "vehicles[].commute_one_way_km"
    assert "Company name" not in report.filled
    assert page.locator("#company-name").input_value() == ""


def test_discover_fields_groups_fragmented_radiogroups_under_shared_parent(page):
    # "New"/"Used"/"Demo under 5,000 kms" are each their own separate
    # role="radiogroup" (one radio each) instead of one group with three
    # options -- confirmed on a real site (Aviva). Their shared parent
    # carries the real question as its own aria-label and must be
    # discovered exactly once, as one field, not three fragments.
    pairs = discover_fields(page)
    labels = [label for label, _ in pairs]

    assert labels.count("What was the condition of your car when you got it") == 1
    assert "New" not in labels
    assert "Used" not in labels
    assert "Demo under 5,000 kms" not in labels

    control = dict(pairs)["What was the condition of your car when you got it"]
    assert control.get_attribute("id") == "fragmented-condition"


def test_discover_fields_does_not_rediscover_a_grouped_radio_input_by_its_own_aria_label(page):
    # "#fragmented-condition-inputs" uses real <input role="radio"
    # aria-label="..."> options (unlike #fragmented-condition's plain
    # <span> text, which has no aria-label of its own and so never
    # exercised this bug) -- confirmed on a real site (Aviva). Once
    # grouped under its shared parent, each option's own aria-label
    # ("New"/"Used") must not surface it a second time as its own
    # spurious standalone field.
    pairs = discover_fields(page)
    labels = [label for label, _ in pairs]

    assert labels.count("Real condition question") == 1
    assert "New" not in labels
    assert "Used" not in labels


def test_discover_fields_excludes_a_grouped_radio_even_if_its_marker_is_lost(page):
    # Confirmed on a real site (Aviva) that clicking one fragment's radio
    # can trigger the underlying framework (Angular) to swap that one
    # element for a fresh instance between separate Playwright round-
    # trips within a single discover_fields() call -- silently losing the
    # discovered-marker attribute set on the old element. Simulates that
    # exact loss directly (strip the marker right after it's set) to
    # verify the live DOM-containment check still excludes it, since it
    # doesn't depend on the marker surviving at all.
    discover_fields(page)  # first pass: groups and marks normally
    page.evaluate(
        """() => {
            document.querySelectorAll('#fragmented-condition-inputs [role="radio"]')
                .forEach((el) => el.removeAttribute('data-qa-agent-discovered'));
        }"""
    )

    pairs = discover_fields(page)
    labels = [label for label, _ in pairs]

    # The parent's own marker is untouched, so it correctly doesn't
    # re-add "Real condition question" a second time -- the point of this
    # test is that stripping the *radio's* marker alone still isn't
    # enough to leak it back in as its own spurious field.
    assert "New" not in labels
    assert "Used" not in labels


def test_fill_visible_fields_fills_a_fragmented_radiogroup(page):
    intake = make_intake()

    def llm_fallback(label: str) -> str | None:
        return "vehicles[].new_or_used_at_purchase" if "condition of your car" in label else None

    intake.vehicles[0].new_or_used_at_purchase = "used"
    report = fill_visible_fields(page, intake, llm_fallback=llm_fallback)

    assert report.filled["What was the condition of your car when you got it"] == "vehicles[].new_or_used_at_purchase"
    checked = page.locator("#fragmented-condition [role='radio'][aria-checked='true']")
    assert checked.inner_text() == "Used"


def test_discover_fields_does_not_double_count_a_labeled_controls_aria_label(page):
    # "#first-name" is already discovered via its real <label for=...>.
    # If it also happened to carry its own aria-label, it must not show up
    # a second time under that aria-label text too.
    page.evaluate("document.getElementById('first-name').setAttribute('aria-label', 'First Name')")
    pairs = discover_fields(page)

    matches = [label for label, control in pairs if control.get_attribute("id") == "first-name"]
    assert matches == ["First Name"]


def test_fill_visible_fields_isolates_a_single_field_interaction_failure(page):
    # "Impossible to satisfy" resolves fine and classifies as a normal
    # RADIO widget, but its only option's text will never match any real
    # value -- confirmed on a real site (Aviva) that this kind of failure,
    # left unguarded, crashes the entire fill_visible_fields call and
    # takes every other field on the page down with it. A short timeout
    # keeps the guaranteed-to-fail click from hanging the test.
    page.set_default_timeout(1000)
    intake = make_intake()

    def llm_fallback(label: str) -> str | None:
        return "vehicles[].primary_use" if label == "Impossible to satisfy" else None

    report = fill_visible_fields(page, intake, llm_fallback=llm_fallback)

    assert "Impossible to satisfy" in report.failed_to_fill
    assert report.filled["First Name"] == "identity.first_name"  # other fields still completed


def test_fill_visible_fields_reports_genuinely_unresolved_labels(page):
    page.evaluate(
        """() => {
            const label = document.createElement('label');
            label.setAttribute('for', 'mystery-field');
            label.textContent = 'Completely novel unmapped question';
            const input = document.createElement('input');
            input.type = 'text';
            input.id = 'mystery-field';
            document.body.appendChild(label);
            document.body.appendChild(input);
        }"""
    )
    intake = make_intake()
    report = fill_visible_fields(page, intake, llm_fallback=None)

    assert "Completely novel unmapped question" in report.unresolved
    assert page.locator("#mystery-field").input_value() == ""


def test_fill_visible_fields_ignores_invisible_recaptcha_infrastructure(page):
    # Confirmed against a real saved page: passive/invisible reCAPTCHA
    # (a script tag, a corner badge, a hidden response field -- present
    # on nearly every modern site, whether or not any challenge is ever
    # shown) makes "recaptcha" appear in the raw HTML source without any
    # visible text a human would actually see. Must not false-positive.
    page.evaluate(
        """() => {
            document.body.innerHTML += `
                <script src="https://www.google.com/recaptcha/api.js" async></script>
                <div class="grecaptcha-badge" style="visibility: hidden;"></div>
                <textarea id="g-recaptcha-response" class="g-recaptcha-response" style="display:none;"></textarea>
            `;
        }"""
    )
    intake = make_intake()

    report = fill_visible_fields(page, intake)  # must not raise CaptchaDetected

    assert page.locator("#first-name").input_value() == "Jane"


def test_fill_visible_fields_raises_on_captcha_without_filling_anything(page):
    page.evaluate(
        "() => { document.body.innerHTML += '<div>Please complete the CAPTCHA below</div>'; }"
    )
    intake = make_intake()

    with pytest.raises(CaptchaDetected):
        fill_visible_fields(page, intake)

    assert page.locator("#first-name").input_value() == ""
