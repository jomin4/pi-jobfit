"""샘플 채용공고 수집기 (ADR-002).

실데이터를 쓸 수 없는 동안 파이프라인 전체를 완성하기 위한 가짜 소스다.
**응답 형태를 고용24와 동일하게 맞추는 것**이 유일한 설계 목표다 —
그래야 나중에 Work24Collector 로 교체할 때 하위 레이어를 한 줄도 안 고친다.

결정성: 같은 seed 면 언제 어디서 돌려도 같은 데이터가 나온다.
그래서 생성물을 커밋하지 않고 생성기만 커밋한다.

난이도: 스킬을 표준명 그대로 쓰지 않는다. 별칭·오타·함정 문구를 섞어
스킬 추출기가 실제로 어려운 문제를 풀게 만든다. 정답은 ground_truth() 로 꺼낸다.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar

import yaml

from jobfit.collectors.base import JobCollector, ListQuery
from jobfit.collectors.budget import CallBudget
from jobfit.paths import SAMPLE_DIR, SKILLS_SEED

_JOSA = {"을": "를", "이": "가", "은": "는", "과": "와"}
_JOSA_RE = re.compile(r"([가-힣A-Za-z0-9#+\.])(을|를|이|가|은|는|과|와)(?=\s|$)")
_SOURCE_ID = re.compile(r"^SAMPLE-(\d{6})$")


def _has_batchim(ch: str) -> bool:
    """받침 유무. 조사 선택에 쓴다."""
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    if ch.isascii() and ch.isalpha():
        return ch.lower() not in "aeiouy"
    return ch.isdigit()


def _fix_josa(text: str) -> str:
    """앞 글자 받침에 맞춰 조사를 고친다. 영문 스킬명이 섞여도 읽히게."""

    def repl(m: re.Match[str]) -> str:
        head, josa = m.group(1), m.group(2)
        pair = {v: k for k, v in _JOSA.items()} | _JOSA
        with_batchim = josa if josa in _JOSA else pair[josa]
        return head + (with_batchim if _has_batchim(head) else _JOSA[with_batchim])

    return _JOSA_RE.sub(repl, text)


@dataclass(frozen=True)
class GroundTruth:
    """생성 시점에 확정한 정답 스킬. 스킬 추출기 평가에 쓴다."""

    source_id: str
    required: tuple[str, ...]
    preferred: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_vocab() -> dict[str, Any]:
    with (SAMPLE_DIR / "vocab.yaml").open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


@lru_cache(maxsize=1)
def _load_skills() -> dict[str, dict[str, Any]]:
    with SKILLS_SEED.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return {s["name"]: s for s in raw["skills"]}


def _weighted(rng: random.Random, items: list[dict[str, Any]]) -> dict[str, Any]:
    return rng.choices(items, weights=[i["weight"] for i in items], k=1)[0]


def _typo(rng: random.Random, word: str) -> str:
    """인접 문자 교환 오타. 3글자 이상 영문에만 적용한다."""
    if len(word) < 4 or not word.isascii():
        return word
    i = rng.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2 :]


class SampleCollector(JobCollector):
    """고용24 응답 형태의 가짜 공고를 결정적으로 생성한다."""

    source: ClassVar[str] = "sample"
    supports_detail: ClassVar[bool] = True
    max_page_size: ClassVar[int] = 100

    def __init__(
        self,
        total: int = 2500,
        seed: int = 42,
        budget: CallBudget | None = None,
    ) -> None:
        super().__init__(budget)
        self._total = total
        self._seed = seed
        self._truth: dict[str, GroundTruth] = {}

    # ---- 공개 API ---------------------------------------------------------

    @property
    def total(self) -> int:
        return self._total

    def ground_truth(self, source_id: str) -> GroundTruth | None:
        """정답 스킬. 해당 공고를 한 번이라도 생성했어야 값이 있다."""
        if source_id not in self._truth:
            idx = self._index_of(source_id)
            if idx is None:
                return None
            self._build(idx)
        return self._truth.get(source_id)

    # ---- JobCollector 구현 ------------------------------------------------

    def _fetch_list(self, query: ListQuery) -> tuple[list[tuple[str, dict[str, Any]]], int]:
        size = min(query.page_size, self.max_page_size)
        start = max(query.page - 1, 0) * size
        rows: list[tuple[str, dict[str, Any]]] = []
        for idx in range(start, min(start + size, self._total)):
            detail = self._build(idx)
            rows.append((detail["wantedAuthNo"], _to_list_row(detail)))
        return rows, self._total

    def _fetch_detail(self, source_id: str) -> dict[str, Any] | None:
        idx = self._index_of(source_id)
        return None if idx is None else self._build(idx)

    # ---- 생성 -------------------------------------------------------------

    def _index_of(self, source_id: str) -> int | None:
        m = _SOURCE_ID.match(source_id)
        if not m:
            return None
        idx = int(m.group(1))
        return idx if 0 <= idx < self._total else None

    def _build(self, idx: int) -> dict[str, Any]:
        """idx 하나가 공고 하나. 같은 idx 는 항상 같은 결과를 낸다."""
        rng = random.Random(self._seed * 1_000_003 + idx)
        v = _load_vocab()
        skills = _load_skills()
        source_id = f"SAMPLE-{idx:06d}"

        role = _weighted(rng, v["roles"])
        region = _weighted(rng, v["regions"])
        industry = _weighted(rng, v["industries"])
        base = rng.choice(v["company_bases"])
        company = rng.choice(v["company_name_forms"]).format(base=base)

        required, preferred = _pick_skills(rng, role)

        career, exp_raw = _career(rng, v)
        sal_tp, sal_raw, sal_min, sal_max = _salary(rng, v)
        close_dt = _deadline(rng, v)
        posted = datetime.now(UTC) - timedelta(days=rng.randrange(0, 60))

        job_cont, said_in_body = _job_content(rng, v, role, company, required, skills)
        # 5~10% 는 본문이 비어 있다. 실데이터에도 이런 공고가 있다.
        if rng.random() < 0.07:
            job_cont, said_in_body = "", []
        certificate, said_in_cert = _lines(rng, v["require_line"], required[:2], skills, 0.35)
        pf_cond, said_in_pref = _lines(rng, v["prefer_line"], preferred, skills, 0.8)
        keywords = list(required[:3])

        # 정답은 "본문에 실제로 쓰인" 스킬만. 어디에도 안 나온 스킬을 정답에 넣으면
        # 추출기가 절대 못 맞히는 문제가 되어 평가가 왜곡된다.
        emitted = set(said_in_body) | set(said_in_cert) | set(keywords)
        self._truth[source_id] = GroundTruth(
            source_id,
            tuple(s for s in required if s in emitted),
            tuple(s for s in preferred if s in set(said_in_pref)),
        )

        return {
            "wantedAuthNo": source_id,
            "corpInfo": {
                "corpNm": company,
                "reperNm": "홍길동",
                "totPsncnt": rng.choice([8, 25, 60, 120, 340, 900]),
                "capitalAmt": rng.randrange(1, 300) * 100_000_000,
                "yrSalesAmt": rng.randrange(5, 5000) * 100_000_000,
                "indTpCdNm": industry["name"],
                "busiCont": f"{industry['name']} 영위 기업",
                "corpAddr": f"{region['name']} 어딘가 1-1",
                "homePg": f"https://www.sample-corp-{idx % 100:03d}.example.com",
                "busiSize": rng.choice(["중소기업", "중견기업", "대기업", "스타트업"]),
            },
            "wantedInfo": {
                "jobsNm": role["category"],
                "wantedTitle": _title(rng, role, company),
                "relJobsNm": role["category"],
                "jobCont": job_cont,
                "receiptCloseDt": close_dt,
                "empTpNm": rng.choices(
                    ["정규직", "계약직", "인턴", "파견직"], weights=[76, 14, 5, 5], k=1
                )[0],
                "collectPsncnt": str(rng.randrange(1, 6)),
                "salTpNm": sal_tp,
                "sal": sal_raw,
                "minSal": str(sal_min) if sal_min else "",
                "maxSal": str(sal_max) if sal_max else "",
                "enterTpNm": exp_raw,
                "eduNm": rng.choices(
                    ["학력무관", "초대졸 이상", "대졸 이상", "석사 이상"],
                    weights=[42, 14, 39, 5],
                    k=1,
                )[0],
                "certificate": certificate,
                "pfCond": pf_cond,
                "etcPfCond": rng.choice(v["trap_phrases"]) if rng.random() < 0.3 else "",
                "workRegion": region["name"],
                "jobsCd": role["jobs_cd"],
                "regionCd": region["code"],
                "minEdubgIcd": rng.choice(["00", "03", "04", "05", "06"]),
                "enterTpCd": career,
                "salTpCd": "Y" if "연" in sal_tp else rng.choice(["M", "H", "D"]),
                "empTpCd": rng.choice(["10", "11", "20"]),
                "dtlRecrContUrl": f"https://sample.local/wanted/{source_id}",
                "keywordList": {"srchKeywordNm": keywords},
            },
            # 개인정보. 베이스 클래스의 scrub_pii 가 적재 전에 제거하는지 확인용으로 일부러 넣는다.
            "empchargeInfo": {
                "empChargerDpt": "인사팀",
                "contactTelno": "02-000-0000",
                "empChargerHp": "010-0000-0000",
                "chargerEmail": "hr@example.com",
            },
            "regDt": posted.strftime("%Y-%m-%d"),
            "smodifyDtm": posted.strftime("%Y%m%d%H%M%S"),
            "infoSvc": "VALIDATION",
        }


# ---- 생성 헬퍼 -------------------------------------------------------------


def _pick_skills(rng: random.Random, role: dict[str, Any]) -> tuple[list[str], list[str]]:
    core = list(role["core"])
    rng.shuffle(core)
    required = core[: rng.randrange(2, min(4, len(core)) + 1)]
    alt = list(role["alt_core"])
    rng.shuffle(alt)
    required += alt[: rng.randrange(0, 3)]
    nice = list(role["nice"])
    rng.shuffle(nice)
    preferred = [s for s in nice[: rng.randrange(1, 4)] if s not in required]
    return required, preferred


def _surface(rng: random.Random, name: str, skills: dict[str, dict[str, Any]]) -> str:
    """표준명 대신 별칭·오타를 섞는다. 추출기 난이도의 핵심."""
    forms = [name, *skills.get(name, {}).get("aliases", [])]
    chosen = str(rng.choice(forms))
    return _typo(rng, chosen) if rng.random() < 0.12 else chosen


def _title(rng: random.Random, role: dict[str, Any], company: str) -> str:
    title = str(rng.choice(role["titles"]))
    if rng.random() < 0.35:
        return f"[{company}] {title} 채용"
    if rng.random() < 0.2:
        return f"{title} (신입/경력)"
    return title


def _job_content(
    rng: random.Random,
    v: dict[str, Any],
    role: dict[str, Any],
    company: str,
    required: list[str],
    skills: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    role_name = rng.choice(role["titles"])
    parts = [rng.choice(v["jobcont_intro"]).format(role=role_name, company=company), ""]
    used = list(required[:3])
    parts += [rng.choice(v["jobcont_task"]).format(skill=_surface(rng, s, skills)) for s in used]
    if rng.random() < 0.3:
        parts += ["", rng.choice(v["trap_phrases"])]
    text = "\n".join(parts)
    if rng.random() < 0.4:
        text += " " + rng.choice(v["noise_snippets"])
    return _fix_josa(text), used


def _lines(
    rng: random.Random,
    templates: list[str],
    names: list[str],
    skills: dict[str, dict[str, Any]],
    prob: float,
) -> tuple[str, list[str]]:
    """생성한 텍스트와, 그 안에 실제로 쓰인 스킬 표준명을 함께 돌려준다."""
    if not names or rng.random() > prob:
        return "", []
    text = "\n".join(rng.choice(templates).format(skill=_surface(rng, n, skills)) for n in names)
    return _fix_josa(text), list(names)


def _career(rng: random.Random, v: dict[str, Any]) -> tuple[str, str]:
    form = _weighted(rng, v["career_forms"])
    lo = rng.randrange(1, 9)
    text = str(rng.choice(form["text"])).format(
        min=lo, max=lo + rng.randrange(2, 5), months=lo * 12
    )
    return str(form["code"]), text


def _salary(rng: random.Random, v: dict[str, Any]) -> tuple[str, str, int | None, int | None]:
    form = _weighted(rng, v["salary_forms"])
    lo = rng.randrange(28, 70) * 100
    hi = lo + rng.randrange(4, 20) * 100
    text = str(rng.choice(form["text"])).format(min=lo, max=hi, month=lo // 12)
    if form["kind"] == "none":
        return "연봉", text, None, None
    if form["kind"] == "range":
        return "연봉", text, lo * 10_000, hi * 10_000
    return "연봉", text, lo * 10_000, None


def _deadline(rng: random.Random, v: dict[str, Any]) -> str:
    form = _weighted(rng, v["deadline_forms"])
    d = datetime.now(UTC) + timedelta(days=rng.randrange(1, 90))
    return str(rng.choice(form["text"])).format(y=d.year, m=f"{d.month:02d}", d=f"{d.day:02d}")


def _to_list_row(detail: dict[str, Any]) -> dict[str, Any]:
    """상세에서 목록 응답 필드만 추린다. 고용24 목록 스키마와 동일하게."""
    info = detail["wantedInfo"]
    corp = detail["corpInfo"]
    return {
        "wantedAuthNo": detail["wantedAuthNo"],
        "company": corp["corpNm"],
        "indTpNm": corp["indTpCdNm"],
        "title": info["wantedTitle"],
        "salTpNm": info["salTpNm"],
        "sal": info["sal"],
        "minSal": info["minSal"],
        "maxSal": info["maxSal"],
        "region": info["workRegion"],
        "minEdubg": info["eduNm"],
        "career": info["enterTpNm"],
        "regDt": detail["regDt"],
        "closeDt": info["receiptCloseDt"],
        "infoSvc": detail["infoSvc"],
        "wantedInfoUrl": info["dtlRecrContUrl"],
        "empTpCd": info["empTpCd"],
        "jobsCd": info["jobsCd"],
        "smodifyDtm": detail["smodifyDtm"],
    }
