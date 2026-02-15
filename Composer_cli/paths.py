from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys

# If running as a PyInstaller bundle, use the executable's directory; otherwise script dir
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
RELEASE_DIR = ARTIFACTS_DIR / "releases"
DEPLOY_DIR = ARTIFACTS_DIR / "packages"
IMAGE_CACHE_DIR = RELEASE_DIR / "images"
PACKET_PROCESSING_DIR = PROJECT_ROOT / "PacketProcessingService"
DOCKER_COMPOSE_DEV_FILE = PROJECT_ROOT / "docker-compose.dev.yml"
DOCKER_COMPOSE_PROD_FILE = PROJECT_ROOT / "docker-compose.prod.yml"
QUESTDB_DIR = PROJECT_ROOT / "QuestDB"

@dataclass(frozen=True)
class Paths:
    project_root: Path = PROJECT_ROOT
    artifacts_dir: Path = ARTIFACTS_DIR
    release_dir: Path = RELEASE_DIR
    deploy_dir: Path = DEPLOY_DIR
    image_cache_dir: Path = IMAGE_CACHE_DIR
    packet_processing_dir: Path = PACKET_PROCESSING_DIR
    compose_dev: Path = DOCKER_COMPOSE_DEV_FILE
    compose_prod: Path = DOCKER_COMPOSE_PROD_FILE
    questdb_dir: Path = QUESTDB_DIR
    video_service_dir: Path = PROJECT_ROOT / "VideoService"
