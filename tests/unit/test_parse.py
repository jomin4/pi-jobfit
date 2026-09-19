"""원문 파싱 단위 테스트. DB 없이 순수 함수만 검증한다.

케이스는 실제 샘플 데이터(data/sample/vocab.yaml)가 만들어내는 표기에서 가져왔다.
실데이터로 갈아타면 여기에 새 표기를 추가하는 것이 첫 작업이 된다.
"""

from datetime import date

import pytest

from jobfit.processing.parse import (
    clean_text,
    normalize_company_name,
    parse_deadline,
    parse_education,
    parse_employment_type,
    parse_experience,
    parse_salary,
)

# ---------- 회사명 ----------


@pytest.mark.parametrize(
    "raw",
    ["(주)카카오", "카카오(주)", "카카오 주식회사", "㈜카카오", "카카오", " 카카오 "],
)
def test_법인격_표기가_달라도_같은_키로_모인다(raw: str) -> None:
    assert normalize_company_name(raw) == "카카오"


def test_빈_회사명은_빈_문자열이_된다() -> None:
    assert normalize_company_name(None) == ""
    assert normalize_company_name("") == ""


# ---------- 본문 정리 ----------


def test_HTML_잔재는_제거되고_섹션_줄바꿈은_남는다() -> None:
    raw = "주요업무<br>- 개발&nbsp;업무\n\n\n\n우대사항"

    cleaned = clean_text(raw)

    assert "<br>" not in cleaned
    assert "&nbsp;" not in cleaned
    # 섹션 구분용 빈 줄은 살아 있어야 한다 (스킬 필수/우대 구분에 쓰인다)
    assert "\n\n" in cleaned
    assert "\n\n\n" not in cleaned


# ---------- 급여 ----------


def test_연봉_범위는_원_단위로_환산된다() -> None:
    result = parse_salary("연 6,900~8,500만원", "Y")

    assert result.min_krw == 69_000_000
    assert result.max_krw == 85_000_000
    assert result.note is None


def test_하한만_있으면_max는_비워둔다() -> None:
    result = parse_salary("연 3600만원 이상", "Y")

    assert result.min_krw == 36_000_000
    assert result.max_krw is None


def test_월급은_12를_곱해_연봉으로_환산한다() -> None:
    result = parse_salary("월 266만원", "M")

    assert result.min_krw == 266 * 10_000 * 12


@pytest.mark.parametrize("raw", ["회사내규에 따름", "면접 후 결정", "협의 후 결정", "추후 협의"])
def test_숫자가_없으면_실패가_아니라_사유를_남긴다(raw: str) -> None:
    result = parse_salary(raw, "Y")

    assert result.min_krw is None
    assert result.note is not None
    assert result.note.startswith("no_number")


def test_시급은_연봉_환산하지_않고_사유를_남긴다() -> None:
    result = parse_salary("시급 12,000원", "H")

    assert result.min_krw is None
    assert result.note is not None
    assert result.note.startswith("hourly")


# ---------- 경력 ----------


@pytest.mark.parametrize("raw,code", [("경력무관", "Z"), ("경력 무관", ""), ("신입/경력", "")])
def test_경력무관은_0년_이상으로_둔다(raw: str, code: str) -> None:
    """NULL 로 두면 'exp_min <= 3' 질의에서 무관 공고가 통째로 빠진다."""
    result = parse_experience(raw, code)

    assert result.min_years == 0
    assert result.max_years is None


def test_신입은_0년_고정이다() -> None:
    result = parse_experience("신입 채용", "N")

    assert (result.min_years, result.max_years) == (0, 0)


def test_범위_표기가_단일_년수보다_먼저_읽힌다() -> None:
    """'3~7년' 에서 뒤의 7만 읽으면 최소 경력이 7년으로 잘못 잡힌다."""
    result = parse_experience("3~7년", "E")

    assert (result.min_years, result.max_years) == (3, 7)


def test_개월_표기는_년으로_내림한다() -> None:
    assert parse_experience("경력 24개월 이상", "E").min_years == 2
    assert parse_experience("경력 30개월 이상", "E").min_years == 2


def test_년차_표기도_읽는다() -> None:
    assert parse_experience("7년차 이상", "E").min_years == 7


def test_읽을_수_없으면_사유를_남긴다() -> None:
    result = parse_experience("담당자 문의", "E")

    assert result.min_years is None
    assert result.note is not None
    assert result.note.startswith("unparsed")


# ---------- 마감일 ----------


@pytest.mark.parametrize("raw", ["2026-10-21", "2026.10.21", "2026/10/21"])
def test_구분자가_달라도_같은_날짜로_읽힌다(raw: str) -> None:
    parsed, note = parse_deadline(raw)

    assert parsed == date(2026, 10, 21)
    assert note is None


@pytest.mark.parametrize("raw", ["상시채용", "채용시까지", "채용시 마감"])
def test_상시채용은_실패가_아니라_open_ended_다(raw: str) -> None:
    parsed, note = parse_deadline(raw)

    assert parsed is None
    assert note == "open_ended"


def test_형식은_맞지만_존재하지_않는_날짜는_거른다() -> None:
    parsed, note = parse_deadline("2026-13-45")

    assert parsed is None
    assert note is not None
    assert note.startswith("invalid_date")


# ---------- 코드 매핑 ----------


def test_학력_코드가_값으로_매핑된다() -> None:
    assert parse_education("04") == "college"
    assert parse_education("00") == "none"


def test_모르는_코드는_예외_대신_None을_돌려준다() -> None:
    """소스가 명세에 없는 새 코드를 보내도 파이프라인이 멈추면 안 된다."""
    assert parse_education("99") is None
    assert parse_education(None) is None
    assert parse_employment_type("ZZ") is None


def test_고용형태_코드가_값으로_매핑된다() -> None:
    assert parse_employment_type("10") == "fulltime"
    assert parse_employment_type("20") == "contract"
