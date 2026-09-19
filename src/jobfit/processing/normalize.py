"""raw payload -> jobs / companies 행으로 변환.

두 단계로 나눈다.
  1) 파이썬: 중첩 JSON 에서 필드를 꺼내고 정규식 파서를 적용해 평면 dict 로 만든다
  2) Polars: 컬럼 단위로 데이터 계약을 검증하고 중복을 접고 품질 지표를 집계한다

왜 나누나: 정규식은 행 단위 작업이라 Polars 로 감싸도 이득이 없다.
반대로 계약 검증·중복 제거·집계는 컬럼 단위라 Polars 가 압도적으로 빠르다.
도구를 맞는 자리에 쓴다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from jobfit.processing.parse import (
    clean_text,
    normalize_company_name,
    parse_deadline,
    parse_education,
    parse_employment_type,
    parse_experience,
    parse_salary,
)

# 데이터 계약 (docs/01-requirements.md 4절)
MAX_TITLE_LENGTH = 300
MAX_EXPERIENCE_YEARS = 40
MIN_ANNUAL_SALARY_KRW = 1_000_000

# 스키마를 고정한다. 값이 전부 NULL 인 컬럼도 타입이 흔들리지 않게 하려는 것.
JOB_SCHEMA: dict[str, pl.DataType] = {
    "source": pl.String(),
    "source_id": pl.String(),
    "company_name": pl.String(),
    "company_name_normalized": pl.String(),
    "industry_name": pl.String(),
    "size_category": pl.String(),
    "homepage": pl.String(),
    "title": pl.String(),
    "description": pl.String(),
    "sections": pl.String(),
    "job_category": pl.String(),
    "employment_type": pl.String(),
    "exp_min": pl.Int16(),
    "exp_max": pl.Int16(),
    "education": pl.String(),
    "salary_min": pl.Int64(),
    "salary_max": pl.Int64(),
    "salary_raw": pl.String(),
    "region_code": pl.String(),
    "region_name": pl.String(),
    "posted_at": pl.Date(),
    "deadline": pl.Date(),
    "url": pl.String(),
    "parse_flags": pl.String(),
}


@dataclass(frozen=True)
class NormalizeResult:
    jobs: pl.DataFrame
    companies: pl.DataFrame
    dropped: int
    fill_rate: dict[str, float]


def flatten_detail(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    """상세 응답 1건을 평면 dict 로 편다. 파싱 실패는 parse_flags 에 모은다."""
    info: dict[str, Any] = payload.get("wantedInfo") or {}
    corp: dict[str, Any] = payload.get("corpInfo") or {}
    flags: dict[str, str] = {}

    salary = parse_salary(info.get("sal"), info.get("salTpCd"))
    if salary.note:
        flags["salary"] = salary.note

    experience = parse_experience(info.get("enterTpNm"), info.get("enterTpCd"))
    if experience.note:
        flags["experience"] = experience.note

    deadline, deadline_note = parse_deadline(info.get("receiptCloseDt"))
    if deadline_note:
        flags["deadline"] = deadline_note

    # 소스가 이미 필드로 나눠준 것을 우리 섹션 이름으로 옮긴다 (api-work24.md 6.1)
    sections = {
        "main_tasks": clean_text(info.get("jobCont")),
        "requirements": clean_text(info.get("certificate")),
        "preferred": clean_text(
            "\n".join(x for x in (info.get("pfCond"), info.get("etcPfCond")) if x)
        ),
    }
    description = "\n\n".join(text for text in sections.values() if text)

    company_name = corp.get("corpNm")
    return {
        "source": source,
        "source_id": payload.get("wantedAuthNo"),
        "company_name": company_name,
        "company_name_normalized": normalize_company_name(company_name),
        "industry_name": corp.get("indTpCdNm"),
        "size_category": corp.get("busiSize"),
        "homepage": corp.get("homePg"),
        "title": info.get("wantedTitle"),
        "description": description or None,
        "sections": json.dumps(sections, ensure_ascii=False),
        "job_category": info.get("jobsNm"),
        "employment_type": parse_employment_type(info.get("empTpCd")),
        "exp_min": experience.min_years,
        "exp_max": experience.max_years,
        "education": parse_education(info.get("minEdubgIcd")),
        "salary_min": salary.min_krw,
        "salary_max": salary.max_krw,
        "salary_raw": info.get("sal"),
        "region_code": info.get("regionCd"),
        "region_name": info.get("workRegion"),
        "posted_at": payload.get("regDt"),
        "deadline": deadline,
        "url": info.get("dtlRecrContUrl"),
        "parse_flags": json.dumps(flags, ensure_ascii=False) if flags else None,
    }


def build_frame(rows: Sequence[dict[str, Any]]) -> pl.DataFrame:
    """평면 dict 목록을 스키마 고정 DataFrame 으로 만든다."""
    if not rows:
        # 빈 입력에도 컬럼 구조는 유지해야 뒤 단계가 KeyError 없이 통과한다
        return pl.DataFrame(schema=JOB_SCHEMA)

    # posted_at 은 원문이 "2026-08-16" 문자열이라 Date 로 바로 못 만든다.
    # 문자열로 받아서 다음 줄에서 파싱한다 — 생성과 변환을 분리한다.
    construction = {name: dtype for name, dtype in JOB_SCHEMA.items() if name != "posted_at"}
    frame = pl.DataFrame(rows, schema_overrides=construction)
    return frame.with_columns(
        # 형식이 어긋나면 예외 대신 NULL. 한 건 때문에 배치가 멈추면 안 된다
        pl.col("posted_at").cast(pl.String).str.to_date("%Y-%m-%d", strict=False)
    )


def apply_contract(frame: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """데이터 계약을 적용한다.

    식별자/제목이 없으면 **행을 버리고**, 값만 이상하면 **그 컬럼만 NULL** 로 둔다.
    후자를 예외로 처리하면 공고 한 건 때문에 배치 전체가 멈춘다.
    """
    before = frame.height
    kept = frame.filter(
        pl.col("source_id").is_not_null()
        & pl.col("title").is_not_null()
        & pl.col("title").str.len_chars().is_between(1, MAX_TITLE_LENGTH)
    )

    cleaned = kept.with_columns(
        exp_min=pl.when(pl.col("exp_min").is_between(0, MAX_EXPERIENCE_YEARS)).then(
            pl.col("exp_min")
        ),
        salary_min=pl.when(pl.col("salary_min") >= MIN_ANNUAL_SALARY_KRW).then(
            pl.col("salary_min")
        ),
    ).with_columns(
        # exp_max 는 정리된 exp_min 에 의존하므로 단계를 나눈다
        exp_max=pl.when(
            pl.col("exp_max").is_between(0, MAX_EXPERIENCE_YEARS)
            & (pl.col("exp_max") >= pl.col("exp_min").fill_null(0))
        ).then(pl.col("exp_max")),
        salary_max=pl.when(pl.col("salary_max") >= pl.col("salary_min").fill_null(0)).then(
            pl.col("salary_max")
        ),
    )

    # 같은 공고가 배치에 두 번 들어오면 마지막 것만 남긴다 (나중 수집분이 최신)
    deduped = cleaned.unique(subset=["source", "source_id"], keep="last", maintain_order=True)
    return deduped, before - deduped.height


def extract_companies(frame: pl.DataFrame) -> pl.DataFrame:
    """공고 프레임에서 회사만 뽑아 중복을 접는다."""
    return (
        frame.select(
            "company_name",
            "company_name_normalized",
            "industry_name",
            "size_category",
            "homepage",
        )
        .filter(pl.col("company_name_normalized").str.len_chars() > 0)
        .unique(subset=["company_name_normalized"], keep="first", maintain_order=True)
    )


def fill_rate(frame: pl.DataFrame) -> dict[str, float]:
    """컬럼별 값 채움 비율. Phase 1 DoD 의 '필수 필드 누락률' 지표가 된다."""
    total = frame.height
    if total == 0:
        return {}
    nulls = frame.null_count().row(0)
    return {
        name: round(1 - count / total, 4) for name, count in zip(frame.columns, nulls, strict=True)
    }


def normalize_details(source: str, payloads: Sequence[dict[str, Any]]) -> NormalizeResult:
    """상세 응답 묶음을 jobs / companies 프레임으로 변환한다."""
    rows = [flatten_detail(source, payload) for payload in payloads]
    frame = build_frame(rows)
    jobs, dropped = apply_contract(frame)
    return NormalizeResult(
        jobs=jobs,
        companies=extract_companies(jobs),
        dropped=dropped,
        fill_rate=fill_rate(jobs),
    )
