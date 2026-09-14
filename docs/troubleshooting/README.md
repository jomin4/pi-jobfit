# 트러블슈팅 기록

프로젝트를 진행하며 실제로 막혔던 문제와 해결 과정을 기록합니다.
**증상 → 오진 → 진단 방법 → 원인 → 해결 → 재발 방지** 순서로 남깁니다.

진단 *방법*을 남기는 게 핵심입니다. 같은 증상이 다른 원인에서 나올 수 있으므로,
"이 명령으로 확인한다"가 "이렇게 고친다"보다 오래 쓰입니다.

| ID | 제목 | Phase | 증상 키워드 |
|---|---|---|---|
| [TS-001](TS-001-editable-install-empty.md) | editable 설치가 빈 껍데기로 남는 문제 | 0 | `ModuleNotFoundError: No module named 'jobfit'` |
| [TS-002](TS-002-postgres-port-conflict.md) | 네이티브 PostgreSQL과의 5432 포트 충돌 | 0 | `password authentication failed`, 깨진 한글 에러 |
| [TS-003](TS-003-precommit-cp949.md) | pre-commit 설정의 한글 주석이 cp949로 깨짐 (+훅 버전·PATH·CRLF) | 0 | `UnicodeDecodeError: cp949`, `no files to check`, `mypy not found` |
| [TS-004](TS-004-action-major-tag.md) | GitHub Action에 이동 major 태그가 없어 워크플로 즉시 실패 | 0 | `Unable to resolve action`, 6초 만의 실패 |

## 새 항목 작성 규칙
- 파일명: `TS-NNN-짧은-영문-슬러그.md`
- 해결하자마자 쓴다. 나중에 쓰면 "왜 그렇게 판단했는지"가 사라진다.
- 명령어와 **실제 출력**을 같이 남긴다.
