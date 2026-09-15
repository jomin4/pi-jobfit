"""data/skills_seed.yaml 을 skills 테이블에 적재한다.

멱등하다 — 여러 번 돌려도 canonical_name 기준으로 갱신만 된다.

    python scripts/seed_skills.py
"""

import sys
from typing import Any

import yaml
from sqlalchemy.dialects.postgresql import insert

from jobfit.db.base import SessionLocal
from jobfit.db.models import Skill
from jobfit.paths import SKILLS_SEED

VALID_CATEGORIES = {"language", "framework", "database", "cloud", "tool", "soft", "domain"}


def load() -> list[dict[str, Any]]:
    with SKILLS_SEED.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return list(raw["skills"])


def validate(rows: list[dict[str, Any]]) -> list[str]:
    """DB에 넣기 전에 사전 자체의 오류를 잡는다."""
    problems: list[str] = []
    seen: set[str] = set()
    alias_owner: dict[str, str] = {}
    for row in rows:
        name = row["name"]
        if name in seen:
            problems.append(f"표준명 중복: {name}")
        seen.add(name)
        if row["category"] not in VALID_CATEGORIES:
            problems.append(f"알 수 없는 카테고리: {name} -> {row['category']}")
        for alias in row.get("aliases") or []:
            key = alias.lower()
            if key in alias_owner:
                problems.append(f"별칭 충돌: {alias} ({alias_owner[key]} / {name})")
            alias_owner[key] = name
            if key == name.lower():
                problems.append(f"별칭이 표준명과 같음: {name}")
    return problems


def main() -> int:
    rows = load()
    if problems := validate(rows):
        for p in problems:
            print(f"[!] {p}")
        return 1

    values = [
        {
            "canonical_name": r["name"],
            "category": r["category"],
            "aliases": r.get("aliases") or [],
            "match_patterns": r.get("patterns"),
            "is_active": True,
        }
        for r in rows
    ]

    stmt = insert(Skill).values(values)
    # 이미 있는 스킬은 별칭/패턴만 갱신한다 (사전은 계속 다듬어지므로)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Skill.canonical_name],
        set_={
            "aliases": stmt.excluded.aliases,
            "category": stmt.excluded.category,
            "match_patterns": stmt.excluded.match_patterns,
            "is_active": stmt.excluded.is_active,
        },
    )

    with SessionLocal() as session:
        session.execute(stmt)
        session.commit()
        total = session.query(Skill).count()

    by_category: dict[str, int] = {}
    for r in rows:
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1
    print(f"적재 완료: {len(values)}건 · 테이블 총 {total}건")
    for cat, n in sorted(by_category.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:10s} {n:3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
