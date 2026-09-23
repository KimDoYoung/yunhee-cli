import os
from pathlib import Path

from dotenv import load_dotenv

# config.py 기준 2단계 위 = 프로젝트 루트 (src/yunhee/config.py -> src/yunhee -> src -> root)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env.local"

# `uv tool install --editable`로 어디서 실행하든 항상 이 프로젝트의 .env.local을 읽는다.
load_dotenv(ENV_FILE)

# OLLAMA_HOST는 Ollama 서버 자체의 bind address 환경변수와 이름이 겹치므로
# (예: OLLAMA_HOST=0.0.0.0) YUNHEE_ 접두사로 구분한다.
OLLAMA_HOST = os.getenv("YUNHEE_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("YUNHEE_OLLAMA_MODEL", "qwen2.5-coder:14b")
EMBED_MODEL = os.getenv("YUNHEE_EMBED_MODEL", "bge-m3:latest")

# docs/docker-compose.yml의 chromadb 서비스 참고
CHROMA_HOST = os.getenv("YUNHEE_CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("YUNHEE_CHROMA_PORT", "8000"))
