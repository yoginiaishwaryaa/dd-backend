import httpx
from app.services.github_api.auth import get_installation_access_token


# Fetches repository details from GitHub API
async def get_repo_details(installation_id: int, owner: str, repo_name: str):
    access_token = await get_installation_access_token(installation_id)

    async with httpx.AsyncClient() as client:
        repo_res = await client.get(
            f"https://api.github.com/repos/{owner}/{repo_name}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

        if repo_res.status_code != 200:
            raise Exception(f"GitHub API Error: {repo_res.text}")

        # Fetches details about the repository to display in dashboard
        data = repo_res.json()

        return {
            "name": data.get("full_name"),
            "description": data.get("description"),
            "language": data.get("language"),
            "stargazers_count": data.get("stargazers_count"),
            "forks_count": data.get("forks_count"),
            "avatar_url": (data.get("owner") or {}).get("avatar_url"),
        }


# Creates a Pull Request for auto-generated documentation updates
async def create_docs_pull_request(
    installation_id: int,
    repo_full_name: str,
    head_branch: str,
    base_branch: str,
    pr_number: int,
    drift_summary: str | None = None,
    updates_summary: str | None = None,
) -> int | None:
    try:
        access_token = await get_installation_access_token(installation_id)

        title = f"Docs: Resolve Documentation Drift for PR #{pr_number}"
        drift_summary_section = f"### Drift Summary\n{drift_summary}\n\n" if drift_summary else ""
        updates_summary_section = (
            f"### Documentation Updates Summary\n{updates_summary}\n\n" if updates_summary else ""
        )
        body = (
            f"## Delta Documentation Update\n\n"
            f"Documentation drift was found in #{pr_number}\n\n"
            f"{drift_summary_section}"
            f"{updates_summary_section}"
            f"**Original PR:** [{repo_full_name}#{pr_number}]"
            f"(https://github.com/{repo_full_name}/pull/{pr_number})\n\n"
            f"_This PR was automatically created by Delta._"
        )

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/pulls",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "title": title,
                    "body": body,
                    "head": head_branch,
                    "base": base_branch,
                },
            )

            if res.status_code == 201:
                data = res.json()
                return data.get("number")
            elif res.status_code == 422:
                # PR may already exist - log and return None instead of raising
                print(f"PR already exists or validation error: {res.text}")
                return None
            else:
                print(f"Error creating docs PR: {res.status_code} - {res.text}")
                return None

    except Exception as e:
        print(f"Exception in create_docs_pull_request: {str(e)}")
        return None


# Requests a review from a GH user on generated PR
async def request_pr_review(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    reviewer: str,
) -> bool:
    try:
        access_token = await get_installation_access_token(installation_id)

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/requested_reviewers",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"reviewers": [reviewer]},
            )

            if res.status_code not in (200, 201):
                print(f"Error requesting review from {reviewer}: {res.text}")
                return False

            return True

    except Exception as e:
        print(f"Exception in request_pr_review: {str(e)}")
        return False


# Fetches a details for a specific commit
async def get_commit(installation_id: int, repo_full_name: str, sha: str) -> dict | None:
    try:
        access_token = await get_installation_access_token(installation_id)

        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/commits/{sha}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            if res.status_code != 200:
                print(f"Error fetching commit {sha}: {res.text}")
                return None

            return res.json()

    except Exception as e:
        print(f"Exception in get_commit: {str(e)}")
        return None
