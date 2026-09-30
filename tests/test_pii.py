import pytest

from app.pii import scrub_text, summarize_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD của tôi là 012345678901")
    assert "012345678901" not in out
    assert "REDACTED_CCCD" in out


@pytest.mark.parametrize(
    "card", ["4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"]
)
def test_scrub_credit_card_formats(card: str) -> None:
    out = scrub_text(f"Card: {card}")
    assert card not in out
    assert "REDACTED_CREDIT_CARD" in out
    # The card must not be split into a phone/CCCD match.
    assert "REDACTED_PHONE_VN" not in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport B1234567")
    assert "B1234567" not in out
    assert "REDACTED_PASSPORT" in out


def test_scrub_multiple_pii_in_one_message() -> None:
    out = scrub_text("mail test@example.com, phone 0901234567, card 4111 1111 1111 1111")
    for raw in ("test@example.com", "0901234567", "4111 1111 1111 1111"):
        assert raw not in out


def test_scrub_keeps_normal_text() -> None:
    text = "How do I debug tail latency with P95 and P99?"
    assert scrub_text(text) == text


def test_summarize_text_scrubs_before_truncating() -> None:
    out = summarize_text("x" * 70 + " test@example.com", max_len=80)
    assert "test@" not in out
