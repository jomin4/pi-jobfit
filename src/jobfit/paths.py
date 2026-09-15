"""프로젝트 경로. 실행 위치에 상관없이 data/ 를 찾기 위해 파일 기준으로 계산한다."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
SKILLS_SEED = DATA_DIR / "skills_seed.yaml"
