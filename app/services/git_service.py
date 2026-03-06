import subprocess
from pathlib import Path
from typing import Optional
from app.core.config import settings


# Utility function to get local path for a cloned repository
def get_local_repo_path(repo_full_name: str) -> Path:
    owner, repo_name = repo_full_name.split("/")
    repos_base = Path(settings.REPOS_BASE_PATH)
    return repos_base / owner / repo_name


# Clones a repository on linking a repository
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


# Removes a cloned repository when a repository is unlinked
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


# Pulls the latest changes for the specified branches in a cloned repository (on PR creation/update)
async def pull_branches(repo_full_name: str, access_token: str, branches: list[str]) -> bool:
    try:
        repo_path = get_local_repo_path(repo_full_name)

        if not repo_path.exists():
            return False

        # Construct the remote URL with the access token for authentication
        remote_url = f"https://x-access-token:{access_token}@github.com/{repo_full_name}.git"

        # Update the remote URL to ensure fetch and pull works
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "set-url", "origin", remote_url],
            capture_output=True,
            text=True,
            timeout=50,
        )

        if result.returncode != 0:
            print(f"Failed to set remote URL for {repo_full_name}: {result.stderr}")
            return False

        # Fetch the latest changes from the remote
        result = subprocess.run(
            ["git", "-C", str(repo_path), "fetch", "origin"],
            capture_output=True,
            text=True,
            timeout=500,
        )

        if result.returncode != 0:
            print(f"Failed to fetch branches for {repo_full_name}: {result.stderr}")
            return False

        # Pull the latest changes for each specified branch
        for branch in branches:
            # Checkout the branch before pulling
            result = subprocess.run(
                ["git", "-C", str(repo_path), "checkout", branch],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Pull the latest changes for the branch
            if result.returncode == 0:
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "pull", "origin", branch],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

            if result.returncode != 0:
                print(f"Failed to pull branch {branch} for {repo_full_name}: {result.stderr}")
                continue
        return True

    except subprocess.TimeoutExpired:
        print(f"Timeout while pulling branches for repository: {repo_full_name}")
        return False
    except Exception as e:
        print(f"Error pulling branches for repository {repo_full_name}: {str(e)}")
        return False
