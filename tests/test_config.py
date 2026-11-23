from app.config import Settings


def test_defaults_are_valid(monkeypatch):
    for key in ["BUDGET_MIN", "BUDGET_MAX", "CITIES", "TIMEZONE", "DAILY_REPORT_TIME"]:
        monkeypatch.delenv(key, raising=False)
    s = Settings()
    assert s.validate() == []
    assert s.budget_min == 1_000_000
    assert s.budget_max == 1_800_000
    assert s.cities == ("פתח תקווה",)
    assert s.daily_report_time == "08:00"


def test_budget_from_env_with_commas(monkeypatch):
    monkeypatch.setenv("BUDGET_MIN", "1,200,000")
    monkeypatch.setenv("BUDGET_MAX", "2,000,000")
    s = Settings()
    assert (s.budget_min, s.budget_max) == (1_200_000, 2_000_000)


def test_invalid_budget_range_reported(monkeypatch):
    monkeypatch.setenv("BUDGET_MIN", "2000000")
    monkeypatch.setenv("BUDGET_MAX", "1000000")
    assert any("BUDGET_MAX" in p for p in Settings().validate())


def test_multiple_cities(monkeypatch):
    monkeypatch.setenv("CITIES", "פתח תקווה; רמת גן")
    assert Settings().cities == ("פתח תקווה", "רמת גן")


def test_bad_report_time(monkeypatch):
    monkeypatch.setenv("DAILY_REPORT_TIME", "25:00")
    assert any("DAILY_REPORT_TIME" in p for p in Settings().validate())


def test_telegram_not_configured_without_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    assert Settings().telegram_configured is False
