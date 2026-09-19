"""정규화 단위 테스트. Polars 변환만 보므로 DB 가 필요 없다."""

import json
from typing import Any

import polars as pl

from jobfit.processing.normalize import (
    apply_contract,
    build_frame,
    extract_companies,
    fill_rate,
    flatten_detail,
    normalize_details,
)


def _payload(**overrides: Any) -> dict[str, Any]:
    """고용24 상세 응답 모양의 최소 페이로드."""
    info: dict[str, Any] = {
        "wantedTitle": "백엔드 개발자",
        "jobCont": "Python 기반 API 개발",
        "certificate": "",
        "pfCond": "AWS 우대",
        "etcPfCond": "",
        "sal": "연 4000~5000만원",
        "salTpCd": "Y",
        "enterTpNm": "경력 3년 이상",
        "enterTpCd": "E",
        "receiptCloseDt": "2026-10-01",
        "minEdubgIcd": "05",
        "empTpCd": "10",
        "jobsNm": "백엔드",
        "regionCd": "11000",
        "workRegion": "서울특별시",
        "dtlRecrContUrl": "https://example.com/1",
    }
    info.update(overrides.pop("info", {}))
    corp: dict[str, Any] = {
        "corpNm": "(주)테스트",
        "indTpCdNm": "정보서비스업",
        "busiSize": "중소기업",
        "homePg": "https://example.com",
    }
    corp.update(overrides.pop("corp", {}))
    base = {
        "wantedAuthNo": "SAMPLE-000001",
        "wantedInfo": info,
        "corpInfo": corp,
        "regDt": "2026-09-01",
    }
    base.update(overrides)
    return base


# ---------- flatten ----------


def test_중첩_JSON이_평면_dict로_펴진다() -> None:
    row = flatten_detail("sample", _payload())

    assert row["source_id"] == "SAMPLE-000001"
    assert row["company_name_normalized"] == "테스트"
    assert row["exp_min"] == 3
    assert row["salary_min"] == 40_000_000
    assert row["education"] == "bachelor"
    assert row["employment_type"] == "fulltime"


def test_파서가_흘린_사유가_parse_flags로_모인다() -> None:
    row = flatten_detail(
        "sample",
        _payload(info={"sal": "회사내규에 따름", "receiptCloseDt": "상시채용"}),
    )

    flags = json.loads(row["parse_flags"])
    assert flags["salary"].startswith("no_number")
    assert flags["deadline"] == "open_ended"


def test_문제가_없으면_parse_flags는_비어_있다() -> None:
    assert flatten_detail("sample", _payload())["parse_flags"] is None


def test_우대조건_두_필드가_한_섹션으로_합쳐진다() -> None:
    row = flatten_detail(
        "sample", _payload(info={"pfCond": "AWS 우대", "etcPfCond": "Docker 우대"})
    )

    preferred = json.loads(row["sections"])["preferred"]
    assert "AWS" in preferred
    assert "Docker" in preferred


# ---------- frame ----------


def test_빈_입력에도_컬럼_구조는_유지된다() -> None:
    frame = build_frame([])

    assert frame.height == 0
    assert "source_id" in frame.columns
    assert frame.schema["exp_min"] == pl.Int16


def test_문자열_날짜가_Date로_변환된다() -> None:
    frame = build_frame([flatten_detail("sample", _payload())])

    assert frame.schema["posted_at"] == pl.Date
    assert str(frame["posted_at"][0]) == "2026-09-01"


# ---------- contract ----------


def test_제목이_없으면_행을_버린다() -> None:
    rows = [
        flatten_detail("sample", _payload()),
        flatten_detail("sample", _payload(wantedAuthNo="X", info={"wantedTitle": None})),
    ]

    kept, dropped = apply_contract(build_frame(rows))

    assert kept.height == 1
    assert dropped == 1


def test_값만_이상하면_행은_살리고_컬럼만_비운다() -> None:
    """공고 한 건 때문에 배치 전체가 멈추면 안 된다."""
    frame = build_frame([flatten_detail("sample", _payload())]).with_columns(
        exp_min=pl.lit(99, dtype=pl.Int16),  # 40년 상한 초과
        salary_min=pl.lit(1000, dtype=pl.Int64),  # 100만원 미만
    )

    kept, dropped = apply_contract(frame)

    assert dropped == 0
    assert kept.height == 1
    assert kept["exp_min"][0] is None
    assert kept["salary_min"][0] is None


def test_같은_공고가_두_번_들어오면_마지막_것만_남는다() -> None:
    old = flatten_detail("sample", _payload(info={"wantedTitle": "예전 제목"}))
    new = flatten_detail("sample", _payload(info={"wantedTitle": "최신 제목"}))

    kept, _ = apply_contract(build_frame([old, new]))

    assert kept.height == 1
    assert kept["title"][0] == "최신 제목"


# ---------- companies ----------


def test_표기가_다른_같은_회사는_한_행으로_접힌다() -> None:
    rows = [
        flatten_detail("sample", _payload(wantedAuthNo="A", corp={"corpNm": "(주)카카오"})),
        flatten_detail("sample", _payload(wantedAuthNo="B", corp={"corpNm": "카카오(주)"})),
        flatten_detail("sample", _payload(wantedAuthNo="C", corp={"corpNm": "㈜네이버"})),
    ]
    frame, _ = apply_contract(build_frame(rows))

    companies = extract_companies(frame)

    assert companies.height == 2
    assert set(companies["company_name_normalized"]) == {"카카오", "네이버"}


# ---------- 지표 ----------


def test_채움_비율이_컬럼별로_계산된다() -> None:
    rows = [
        flatten_detail("sample", _payload(wantedAuthNo="A")),
        flatten_detail("sample", _payload(wantedAuthNo="B", info={"sal": "회사내규에 따름"})),
    ]
    frame, _ = apply_contract(build_frame(rows))

    rates = fill_rate(frame)

    assert rates["source_id"] == 1.0
    assert rates["salary_min"] == 0.5


def test_전체_파이프라인이_한_번에_돈다() -> None:
    payloads = [_payload(wantedAuthNo=f"SAMPLE-{i:06d}") for i in range(5)]

    result = normalize_details("sample", payloads)

    assert result.jobs.height == 5
    assert result.companies.height == 1
    assert result.dropped == 0
