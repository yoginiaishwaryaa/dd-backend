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


# Creates a docs branch from the original PR branch for doc generation
async def checkout_docs_branch(
    repo_path: str, original_branch: str, access_token: str, repo_full_name: str
) -> Optional[str]:
    try:
        path = Path(repo_path)
        if not path.exists():
            print(f"Repository path not found: {repo_path}")
            return None

        # Set the remote URL with the access token for authentication
        remote_url = f"https://x-access-token:{access_token}@github.com/{repo_full_name}.git"
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "set-url", "origin", remote_url],
            capture_output=True,
            text=True,
            timeout=50,
        )
        if result.returncode != 0:
            print(f"Failed to set remote URL: {result.stderr}")
            return None

        # Fetch latest changes from origin
        result = subprocess.run(
            ["git", "-C", repo_path, "fetch", "origin"],
            capture_output=True,
            text=True,
            timeout=500,
        )
        if result.returncode != 0:
            print(f"Failed to fetch origin: {result.stderr}")
            return None

        # Checkout the original branch
        result = subprocess.run(
            ["git", "-C", repo_path, "checkout", original_branch],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"Failed to checkout {original_branch}: {result.stderr}")
            return None

        # Pull latest changes on original branch
        subprocess.run(
            ["git", "-C", repo_path, "pull", "origin", original_branch],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Build the docs branch name
        docs_branch = f"docs/drift-fix/{original_branch}"

        # Try to create the new branch; if it already exists append a timestamp
        result = subprocess.run(
            ["git", "-C", repo_path, "checkout", "-b", docs_branch],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            # Branch already exists — append a timestamp for uniqueness
            import time

            timestamp = int(time.time())
            docs_branch = f"docs/drift-fix/{original_branch}-{timestamp}"
            result = subprocess.run(
                ["git", "-C", repo_path, "checkout", "-b", docs_branch],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                print(f"Failed to create docs branch {docs_branch}: {result.stderr}")
                return None

        return docs_branch

    except subprocess.TimeoutExpired:
        print(f"Timeout while creating docs branch for {repo_full_name}")
        return None
    except Exception as e:
        print(f"Error creating docs branch: {str(e)}")
        return None


# Stages modified .md files, commits, and pushes for doc generation
async def commit_and_push_docs(
    repo_path: str, pr_number: int, access_token: str, repo_full_name: str
) -> bool:
    try:
        path = Path(repo_path)
        if not path.exists():
            print(f"Repository path not found: {repo_path}")
            return False

        # Set the remote URL with the access token for authentication
        remote_url = f"https://x-access-token:{access_token}@github.com/{repo_full_name}.git"
        subprocess.run(
            ["git", "-C", repo_path, "remote", "set-url", "origin", remote_url],
            capture_output=True,
            text=True,
            timeout=50,
        )

        # Stage only .md files
        result = subprocess.run(
            ["git", "-C", repo_path, "add", "*.md"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"Failed to stage .md files: {result.stderr}")
            return False

        # Check if there are any staged changes to commit
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--cached", "--quiet"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # No staged changes — nothing to commit
            print("No .md changes to commit")
            return True

        # Commit with the standardised message
        commit_message = f"docs: auto-resolve drift findings for #{pr_number}"
        result = subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", commit_message],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"Failed to commit: {result.stderr}")
            return False

        # Get the current branch name for the push
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"Failed to get current branch: {result.stderr}")
            return False

        current_branch = result.stdout.strip()

        # Push to origin
        result = subprocess.run(
            ["git", "-C", repo_path, "push", "origin", current_branch],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"Failed to push: {result.stderr}")
            return False

        return True

    except subprocess.TimeoutExpired:
        print(f"Timeout while committing/pushing docs for {repo_full_name}")
        return False
    except Exception as e:
        print(f"Error committing/pushing docs: {str(e)}")
        return False
