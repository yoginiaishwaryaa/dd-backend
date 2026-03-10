from pathlib import Path
from app.core.config import settings


# Builds the path to the local repository
def get_local_repo_path(repo_full_name: str) -> Path:
    owner, repo_name = repo_full_name.split("/")
    repos_base = Path(settings.REPOS_BASE_PATH)
    return repos_base / owner / repo_name
