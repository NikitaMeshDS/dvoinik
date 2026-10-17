from urllib.parse import urlparse

from dvoinik.population import SEGMENT_SOURCES, SEGMENTS, SOURCE_GAPS

STATUSES = {"согласуется", "ориентир", "устарело"}


def test_sources_reference_known_segments_with_full_citations():
    assert set(SEGMENT_SOURCES) <= set(SEGMENTS)
    for items in SEGMENT_SOURCES.values():
        assert items
        for item in items:
            assert set(item) == {"fact", "use", "status", "source", "date", "url"}
            assert item["status"] in STATUSES
            assert all(isinstance(v, str) and v.strip() for v in item.values())
            url = urlparse(item["url"])
            assert url.scheme == "https" and url.netloc


def test_gaps_name_every_segment_without_sources():
    missing = [SEGMENTS[s]["name"] for s in SEGMENTS if s not in SEGMENT_SOURCES]
    assert missing, "если источники есть для всех сегментов, обновите SOURCE_GAPS"
    for keyword in ["студентов Москвы", "регионов", "молодых семей"]:
        assert keyword in SOURCE_GAPS
    assert {"student_msk", "student_reg", "young_family"} == set(SEGMENTS) - set(SEGMENT_SOURCES)


def test_consistent_income_claims_match_profiles():
    assert "пенсия 20–35 тыс. ₽" in SEGMENTS["senior"]["income"]
    assert any("200 тыс. ₽" in income for income in SEGMENTS["self_employed"]["income"])


def test_distortion_risk_covers_low_income_segments_only():
    from dvoinik.population import DISTORTION_RISK, RISK_SOURCE

    assert set(DISTORTION_RISK) == {"student_reg", "teen", "senior", "nonresident"}
    assert RISK_SOURCE.startswith("https://arxiv.org/")
