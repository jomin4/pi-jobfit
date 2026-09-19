"""원문 필드 -> 정형 값 파싱. 순수 함수만 둔다 (I/O 없음).

설계 규칙 하나: **파싱 실패로 예외를 던지지 않는다.**
"회사내규에 따름" 같은 값은 버그가 아니라 정상 입력이다. 값은 None 으로 두고
사유를 note 에 담아 돌려준다. 호출부가 jobs.parse_flags 에 모아 기록하고,
그 비율이 곧 Phase 1 DoD 의 "파싱 성공률" 지표가 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MAN_WON = 10_000
_MONTHS_PER_YEAR = 12

_CORP_FORMS = re.compile(r"(\(주\)|㈜|주식회사|\(유\)|유한회사|\(재\)|재단법인)")
_WS = re.compile(r"\s+")
_HTML_TAG = re.compile(r"<[^>]+>")
_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"'}
_NUMBER = re.compile(r"\d[\d,]*")
_YEAR_RANGE = re.compile(r"(\d+)\s*[~\-–]\s*(\d+)\s*년")
_YEARS = re.compile(r"(\d+)\s*년")
_MONTHS = re.compile(r"(\d+)\s*개월")
_DATE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_OPEN_ENDED = ("상시", "채용시", "수시")

EDUCATION_BY_CODE: dict[str, str] = {
    "00": "none",
    "01": "elementary",
    "02": "middle",
    "03": "highschool",
    "04": "college",
    "05": "bachelor",
    "06": "master",
    "07": "phd",
}

EMPLOYMENT_BY_CODE: dict[str, str] = {
    "10": "fulltime",
    "11": "parttime",
    "20": "contract",
    "21": "contract",
    "4": "dispatch",
}


def clean_text(raw: str | None) -> str:
    """HTML 잔재를 걷어낸다. 줄바꿈은 섹션 구분이라 살린다."""
    if not raw:
        return ""
    text = _HTML_TAG.sub(" ", raw)
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def normalize_company_name(raw: str | None) -> str:
    """법인격과 공백을 지워 같은 회사를 한 키로 모은다.

    (주)카카오 / 카카오(주) / 카카오 주식회사 / ㈜카카오  ->  카카오
    """
    if not raw:
        return ""
    return _WS.sub("", _CORP_FORMS.sub("", raw)).strip()


@dataclass(frozen=True)
class Salary:
    """연봉 범위(원). 파싱 못 하면 값은 None 이고 note 에 사유가 담긴다."""

    min_krw: int | None = None
    max_krw: int | None = None
    note: str | None = None


def parse_salary(raw: str | None, sal_tp_cd: str | None = None) -> Salary:
    """급여 문자열을 연봉 범위(원)로 바꾼다. 월급은 12를 곱해 연봉으로 환산한다."""
    text = (raw or "").strip()
    if not text:
        return Salary(note="empty")

    numbers = [int(m.group().replace(",", "")) for m in _NUMBER.finditer(text)]
    if not numbers:
        return Salary(note=f"no_number:{text[:20]}")

    code = (sal_tp_cd or "").upper()
    if "시급" in text or code == "H":
        return Salary(note=f"hourly:{text[:20]}")
    if "일급" in text or code == "D":
        return Salary(note=f"daily:{text[:20]}")

    values = [n * _MAN_WON for n in numbers]
    if "월" in text or code == "M":
        values = [v * _MONTHS_PER_YEAR for v in values]

    low = min(values)
    high = max(values) if len(values) > 1 else None
    return Salary(min_krw=low, max_krw=high)


@dataclass(frozen=True)
class Experience:
    """경력 요구 범위(년). 무관/신입도 숫자로 표현해 범위 질의에 걸리게 한다."""

    min_years: int | None = None
    max_years: int | None = None
    note: str | None = None


def parse_experience(raw: str | None, enter_tp_cd: str | None = None) -> Experience:
    """경력 문자열을 연 단위 범위로 바꾼다."""
    text = (raw or "").strip()
    code = (enter_tp_cd or "").upper()

    if code == "Z" or "무관" in text or "신입/경력" in text:
        # 누구나 지원 가능. NULL 대신 0년 이상으로 두면 범위 질의에 자연스럽게 걸린다
        return Experience(min_years=0)
    if code == "N" or "신입" in text:
        return Experience(min_years=0, max_years=0)

    if rng := _YEAR_RANGE.search(text):
        return Experience(min_years=int(rng.group(1)), max_years=int(rng.group(2)))
    if months := _MONTHS.search(text):
        return Experience(min_years=int(months.group(1)) // _MONTHS_PER_YEAR)
    if years := _YEARS.search(text):
        return Experience(min_years=int(years.group(1)))
    return Experience(note=f"unparsed:{text[:20]}")


def parse_deadline(raw: str | None) -> tuple[date | None, str | None]:
    """마감일. 상시채용은 실패가 아니라 정상적인 NULL 이다."""
    text = (raw or "").strip()
    if not text:
        return None, "empty"
    if any(keyword in text for keyword in _OPEN_ENDED):
        return None, "open_ended"
    if not (m := _DATE.search(text)):
        return None, f"unparsed:{text[:20]}"
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), None
    except ValueError:
        return None, f"invalid_date:{text[:20]}"


def parse_education(code: str | None) -> str | None:
    return EDUCATION_BY_CODE.get((code or "").strip())


def parse_employment_type(code: str | None) -> str | None:
    return EMPLOYMENT_BY_CODE.get((code or "").strip())
