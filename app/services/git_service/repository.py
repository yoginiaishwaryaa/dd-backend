import subprocess
from typing import Optional
from app.services.git_service.utils import get_local_repo_path


# Clones the repository to repo base path
async def clone_repository(
    repo_full_name: str, access_token: str, target_branch: str = "main"
) -> Optional[str]:
    try:
        repo_path = get_local_repo_path(repo_full_name)
        owner_dir = repo_path.parent

        # Ensure the owner directory exists
        owner_dir.mkdir(parents=True, exist_ok=True)

        # Construct the clone URL with the access token for authentication
        clone_url = f"https://x-access-token:{access_token}@github.com/{repo_full_name}.git"

        # Clone the repository using subprocess to call git
        result = subprocess.run(
            ["git", "clone", "--branch", target_branch, clone_url, str(repo_path)],
            capture_output=True,
            text=True,
            timeout=1000,
        )

        if result.returncode == 0:
            return str(repo_path)
        else:
            print(f"Failed to clone repository {repo_full_name}: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print(f"Timeout while cloning repository: {repo_full_name}")
        return None
    except Exception as e:
        print(f"Error cloning repository {repo_full_name}: {str(e)}")
        return None


# Remove the cloned respository repo base path
def remove_cloned_repository(repo_full_name: str) -> bool:
    try:
        repo_path = get_local_repo_path(repo_full_name)

        # Remove the cloned repository directory if it exists
        if repo_path.exists():
            import shutil

            shutil.rmtree(repo_path)
            return True
        else:
            return False

    except Exception as e:
        print(f"Error removing cloned repository {repo_full_name}: {str(e)}")
        return False
