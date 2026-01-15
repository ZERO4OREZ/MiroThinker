# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
GitHub MCP Server - 提供 GitHub 搜索和内容获取能力

Tools:
    搜索类:
    - github_search_code: 搜索代码
    - github_search_repos: 搜索仓库
    - github_search_issues: 搜索 Issues/PRs

    仓库信息类:
    - github_get_repo_info: 获取仓库基本信息（描述、星标、语言等）
    - github_get_readme: 获取 README 文件内容
    - github_list_languages: 获取仓库使用的编程语言统计

    目录与文件类:
    - github_list_directory: 列出目录内容
    - github_get_file_content: 获取文件内容

    版本与提交类:
    - github_list_releases: 获取发布版本列表
    - github_list_commits: 获取最近提交记录
    - github_list_branches: 获取分支列表
    - github_list_tags: 获取标签列表

    Issues/PR 类:
    - github_get_issue_detail: 获取 Issue 详情
    - github_get_pr_detail: 获取 PR 详情

    贡献者类:
    - github_list_contributors: 获取贡献者列表
"""

import base64
import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"

# Initialize FastMCP server
mcp = FastMCP("github-mcp-server")


def _get_headers():
    """Get common headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
    ),
)
async def _make_github_request(
    endpoint: str,
    params: Optional[dict] = None,
    timeout: float = 30.0,
) -> dict:
    """Make HTTP request to GitHub API with retry logic."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}{endpoint}",
            params=params,
            headers=_get_headers(),
        )
        response.raise_for_status()
        return response.json()


def _format_error(error: Exception) -> str:
    """Format error message for tool response."""
    return json.dumps(
        {"success": False, "error": str(error), "results": []},
        ensure_ascii=False,
    )


@mcp.tool()
async def github_search_code(
    q: str,
    repo: Optional[str] = None,
    language: Optional[str] = None,
    filename: Optional[str] = None,
    extension: Optional[str] = None,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    在 GitHub 上搜索代码。

    Args:
        q: 搜索关键词
        repo: 限定仓库（格式: owner/repo），如 "microsoft/vscode"
        language: 限定编程语言，如 "python", "javascript"
        filename: 限定文件名，如 "config.yaml"
        extension: 限定文件扩展名，如 "py", "js"
        per_page: 每页结果数 (默认 30, 最大 100)
        page: 页码

    Returns:
        JSON 格式的搜索结果，包含匹配的代码片段和文件位置
    """
    if not GITHUB_TOKEN:
        return json.dumps(
            {
                "success": False,
                "error": "GITHUB_TOKEN environment variable not set",
                "results": [],
            },
            ensure_ascii=False,
        )

    if not q or not q.strip():
        return json.dumps(
            {
                "success": False,
                "error": "Search query 'q' is required and cannot be empty",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        # Build query with qualifiers
        query_parts = [q.strip()]
        if repo:
            query_parts.append(f"repo:{repo}")
        if language:
            query_parts.append(f"language:{language}")
        if filename:
            query_parts.append(f"filename:{filename}")
        if extension:
            query_parts.append(f"extension:{extension}")

        query = " ".join(query_parts)

        data = await _make_github_request(
            "/search/code",
            params={"q": query, "per_page": min(per_page, 100), "page": page},
        )

        # Simplify results
        results = []
        for item in data.get("items", []):
            results.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "repository": item.get("repository", {}).get("full_name"),
                "html_url": item.get("html_url"),
                "score": item.get("score"),
            })

        return json.dumps(
            {
                "success": True,
                "total_count": data.get("total_count", 0),
                "results": results,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_search_repos(
    q: str,
    language: Optional[str] = None,
    sort: str = "best-match",
    order: str = "desc",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    在 GitHub 上搜索仓库。

    Args:
        q: 搜索关键词
        language: 限定编程语言，如 "python"
        sort: 排序方式 ("stars", "forks", "help-wanted-issues", "updated", "best-match")
        order: 排序顺序 ("asc", "desc")
        per_page: 每页结果数 (默认 30, 最大 100)
        page: 页码

    Returns:
        JSON 格式的仓库搜索结果
    """
    if not q or not q.strip():
        return json.dumps(
            {
                "success": False,
                "error": "Search query 'q' is required and cannot be empty",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        query_parts = [q.strip()]
        if language:
            query_parts.append(f"language:{language}")

        query = " ".join(query_parts)

        params = {
            "q": query,
            "per_page": min(per_page, 100),
            "page": page,
        }
        if sort != "best-match":
            params["sort"] = sort
            params["order"] = order

        data = await _make_github_request("/search/repositories", params=params)

        # Simplify results
        results = []
        for item in data.get("items", []):
            results.append({
                "full_name": item.get("full_name"),
                "description": item.get("description"),
                "html_url": item.get("html_url"),
                "language": item.get("language"),
                "stargazers_count": item.get("stargazers_count"),
                "forks_count": item.get("forks_count"),
                "open_issues_count": item.get("open_issues_count"),
                "updated_at": item.get("updated_at"),
                "topics": item.get("topics", []),
            })

        return json.dumps(
            {
                "success": True,
                "total_count": data.get("total_count", 0),
                "results": results,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_search_issues(
    q: str,
    repo: Optional[str] = None,
    state: str = "all",
    type: str = "all",
    sort: str = "best-match",
    order: str = "desc",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    在 GitHub 上搜索 Issues 和 Pull Requests。

    Args:
        q: 搜索关键词
        repo: 限定仓库（格式: owner/repo）
        state: 状态筛选 ("open", "closed", "all")
        type: 类型筛选 ("issue", "pr", "all")
        sort: 排序方式 ("comments", "reactions", "created", "updated", "best-match")
        order: 排序顺序 ("asc", "desc")
        per_page: 每页结果数
        page: 页码

    Returns:
        JSON 格式的 Issue/PR 搜索结果
    """
    if not q or not q.strip():
        return json.dumps(
            {
                "success": False,
                "error": "Search query 'q' is required and cannot be empty",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        query_parts = [q.strip()]
        if repo:
            query_parts.append(f"repo:{repo}")
        if state != "all":
            query_parts.append(f"state:{state}")
        if type == "issue":
            query_parts.append("is:issue")
        elif type == "pr":
            query_parts.append("is:pr")

        query = " ".join(query_parts)

        params = {
            "q": query,
            "per_page": min(per_page, 100),
            "page": page,
        }
        if sort != "best-match":
            params["sort"] = sort
            params["order"] = order

        data = await _make_github_request("/search/issues", params=params)

        # Simplify results
        results = []
        for item in data.get("items", []):
            is_pr = "pull_request" in item
            results.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "type": "pr" if is_pr else "issue",
                "html_url": item.get("html_url"),
                "repository": item.get("repository_url", "").replace(
                    "https://api.github.com/repos/", ""
                ),
                "user": item.get("user", {}).get("login"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "comments": item.get("comments"),
                "labels": [label.get("name") for label in item.get("labels", [])],
            })

        return json.dumps(
            {
                "success": True,
                "total_count": data.get("total_count", 0),
                "results": results,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_get_file_content(
    repo: str,
    path: str,
    ref: str = "main",
) -> str:
    """
    获取 GitHub 仓库中的文件内容。

    Args:
        repo: 仓库名称（格式: owner/repo），如 "microsoft/vscode"
        path: 文件路径，如 "src/main.py" 或 "README.md"
        ref: 分支名、tag 或 commit SHA (默认: "main")

    Returns:
        文件内容（文本格式）
    """
    if not repo or not path:
        return json.dumps(
            {
                "success": False,
                "error": "Both 'repo' and 'path' are required",
            },
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/contents/{path}",
            params={"ref": ref},
        )

        # Handle file content
        if data.get("type") == "file":
            content = data.get("content", "")
            encoding = data.get("encoding", "")

            if encoding == "base64":
                try:
                    decoded_content = base64.b64decode(content).decode("utf-8")
                except Exception:
                    decoded_content = "[Binary file - cannot decode as text]"
            else:
                decoded_content = content

            return json.dumps(
                {
                    "success": True,
                    "name": data.get("name"),
                    "path": data.get("path"),
                    "size": data.get("size"),
                    "sha": data.get("sha"),
                    "html_url": data.get("html_url"),
                    "content": decoded_content,
                },
                ensure_ascii=False,
            )
        else:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Path is not a file, it's a {data.get('type')}. Use github_list_directory for directories.",
                },
                ensure_ascii=False,
            )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_directory(
    repo: str,
    path: str = "",
    ref: str = "main",
) -> str:
    """
    列出 GitHub 仓库中目录的内容。

    Args:
        repo: 仓库名称（格式: owner/repo）
        path: 目录路径，空字符串表示根目录
        ref: 分支名、tag 或 commit SHA (默认: "main")

    Returns:
        目录中的文件和子目录列表
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        endpoint = f"/repos/{repo}/contents/{path}" if path else f"/repos/{repo}/contents"
        data = await _make_github_request(endpoint, params={"ref": ref})

        # Handle directory listing
        if isinstance(data, list):
            items = []
            for item in data:
                items.append({
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),  # "file" or "dir"
                    "size": item.get("size") if item.get("type") == "file" else None,
                    "html_url": item.get("html_url"),
                })

            return json.dumps(
                {
                    "success": True,
                    "repo": repo,
                    "path": path or "/",
                    "ref": ref,
                    "items": items,
                },
                ensure_ascii=False,
            )
        else:
            return json.dumps(
                {
                    "success": False,
                    "error": "Path is not a directory. Use github_get_file_content for files.",
                },
                ensure_ascii=False,
            )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_get_issue_detail(
    repo: str,
    issue_number: int,
    include_comments: bool = True,
) -> str:
    """
    获取 GitHub Issue 的详细信息，包括评论。

    Args:
        repo: 仓库名称（格式: owner/repo）
        issue_number: Issue 编号
        include_comments: 是否包含评论 (默认: True)

    Returns:
        Issue 详情和评论
    """
    if not repo or not issue_number:
        return json.dumps(
            {"success": False, "error": "Both 'repo' and 'issue_number' are required"},
            ensure_ascii=False,
        )

    try:
        # Get issue details
        issue_data = await _make_github_request(f"/repos/{repo}/issues/{issue_number}")

        result = {
            "success": True,
            "number": issue_data.get("number"),
            "title": issue_data.get("title"),
            "state": issue_data.get("state"),
            "html_url": issue_data.get("html_url"),
            "user": issue_data.get("user", {}).get("login"),
            "body": issue_data.get("body"),
            "labels": [label.get("name") for label in issue_data.get("labels", [])],
            "created_at": issue_data.get("created_at"),
            "updated_at": issue_data.get("updated_at"),
            "closed_at": issue_data.get("closed_at"),
            "comments_count": issue_data.get("comments"),
        }

        # Get comments if requested
        if include_comments and issue_data.get("comments", 0) > 0:
            comments_data = await _make_github_request(
                f"/repos/{repo}/issues/{issue_number}/comments",
                params={"per_page": 100},
            )
            result["comments"] = [
                {
                    "user": comment.get("user", {}).get("login"),
                    "body": comment.get("body"),
                    "created_at": comment.get("created_at"),
                }
                for comment in comments_data
            ]

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_get_pr_detail(
    repo: str,
    pr_number: int,
    include_comments: bool = True,
    include_files: bool = True,
) -> str:
    """
    获取 GitHub Pull Request 的详细信息，包括评论和文件变更。

    Args:
        repo: 仓库名称（格式: owner/repo）
        pr_number: PR 编号
        include_comments: 是否包含评论 (默认: True)
        include_files: 是否包含变更的文件列表 (默认: True)

    Returns:
        PR 详情、评论和文件变更
    """
    if not repo or not pr_number:
        return json.dumps(
            {"success": False, "error": "Both 'repo' and 'pr_number' are required"},
            ensure_ascii=False,
        )

    try:
        # Get PR details
        pr_data = await _make_github_request(f"/repos/{repo}/pulls/{pr_number}")

        result = {
            "success": True,
            "number": pr_data.get("number"),
            "title": pr_data.get("title"),
            "state": pr_data.get("state"),
            "merged": pr_data.get("merged"),
            "html_url": pr_data.get("html_url"),
            "user": pr_data.get("user", {}).get("login"),
            "body": pr_data.get("body"),
            "head_branch": pr_data.get("head", {}).get("ref"),
            "base_branch": pr_data.get("base", {}).get("ref"),
            "created_at": pr_data.get("created_at"),
            "updated_at": pr_data.get("updated_at"),
            "merged_at": pr_data.get("merged_at"),
            "additions": pr_data.get("additions"),
            "deletions": pr_data.get("deletions"),
            "changed_files": pr_data.get("changed_files"),
        }

        # Get comments if requested
        if include_comments:
            comments_data = await _make_github_request(
                f"/repos/{repo}/issues/{pr_number}/comments",
                params={"per_page": 100},
            )
            result["comments"] = [
                {
                    "user": comment.get("user", {}).get("login"),
                    "body": comment.get("body"),
                    "created_at": comment.get("created_at"),
                }
                for comment in comments_data
            ]

        # Get files if requested
        if include_files:
            files_data = await _make_github_request(
                f"/repos/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100},
            )
            result["files"] = [
                {
                    "filename": file.get("filename"),
                    "status": file.get("status"),  # added, removed, modified, renamed
                    "additions": file.get("additions"),
                    "deletions": file.get("deletions"),
                    "changes": file.get("changes"),
                }
                for file in files_data
            ]

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_releases(
    repo: str,
    per_page: int = 10,
    page: int = 1,
) -> str:
    """
    获取 GitHub 仓库的发布版本列表。

    Args:
        repo: 仓库名称（格式: owner/repo），如 "microsoft/vscode"
        per_page: 每页结果数 (默认 10, 最大 100)
        page: 页码

    Returns:
        JSON 格式的发布版本列表，包含版本号、发布日期、描述等
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/releases",
            params={"per_page": min(per_page, 100), "page": page},
        )

        releases = []
        for item in data:
            releases.append({
                "tag_name": item.get("tag_name"),
                "name": item.get("name"),
                "published_at": item.get("published_at"),
                "html_url": item.get("html_url"),
                "body": item.get("body", "")[:500] if item.get("body") else "",  # Truncate long descriptions
                "prerelease": item.get("prerelease"),
                "draft": item.get("draft"),
                "author": item.get("author", {}).get("login"),
            })

        return json.dumps(
            {
                "success": True,
                "repo": repo,
                "total_returned": len(releases),
                "releases": releases,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_commits(
    repo: str,
    per_page: int = 10,
    page: int = 1,
    sha: str = "main",
) -> str:
    """
    获取 GitHub 仓库的最近提交记录。

    Args:
        repo: 仓库名称（格式: owner/repo）
        per_page: 每页结果数 (默认 10, 最大 100)
        page: 页码
        sha: 分支名或 commit SHA (默认: "main")

    Returns:
        JSON 格式的提交记录列表
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/commits",
            params={"per_page": min(per_page, 100), "page": page, "sha": sha},
        )

        commits = []
        for item in data:
            commit_info = item.get("commit", {})
            commits.append({
                "sha": item.get("sha", "")[:7],  # Short SHA
                "message": commit_info.get("message", "").split("\n")[0],  # First line only
                "author": commit_info.get("author", {}).get("name"),
                "date": commit_info.get("author", {}).get("date"),
                "html_url": item.get("html_url"),
            })

        return json.dumps(
            {
                "success": True,
                "repo": repo,
                "branch": sha,
                "total_returned": len(commits),
                "commits": commits,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_get_repo_info(
    repo: str,
) -> str:
    """
    获取 GitHub 仓库的基本信息。

    Args:
        repo: 仓库名称（格式: owner/repo），如 "microsoft/vscode"

    Returns:
        JSON 格式的仓库信息，包含描述、星标数、fork数、语言、许可证等
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(f"/repos/{repo}")

        return json.dumps(
            {
                "success": True,
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "html_url": data.get("html_url"),
                "homepage": data.get("homepage"),
                "language": data.get("language"),
                "stargazers_count": data.get("stargazers_count"),
                "forks_count": data.get("forks_count"),
                "open_issues_count": data.get("open_issues_count"),
                "watchers_count": data.get("watchers_count"),
                "default_branch": data.get("default_branch"),
                "license": data.get("license", {}).get("name") if data.get("license") else None,
                "topics": data.get("topics", []),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "pushed_at": data.get("pushed_at"),
                "size": data.get("size"),
                "archived": data.get("archived"),
                "disabled": data.get("disabled"),
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_contributors(
    repo: str,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    获取 GitHub 仓库的贡献者列表。

    Args:
        repo: 仓库名称（格式: owner/repo）
        per_page: 每页结果数 (默认 30, 最大 100)
        page: 页码

    Returns:
        JSON 格式的贡献者列表，按贡献数量排序
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/contributors",
            params={"per_page": min(per_page, 100), "page": page},
        )

        contributors = []
        for item in data:
            contributors.append({
                "login": item.get("login"),
                "contributions": item.get("contributions"),
                "html_url": item.get("html_url"),
                "avatar_url": item.get("avatar_url"),
            })

        return json.dumps(
            {
                "success": True,
                "repo": repo,
                "total_returned": len(contributors),
                "contributors": contributors,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_branches(
    repo: str,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    获取 GitHub 仓库的分支列表。

    Args:
        repo: 仓库名称（格式: owner/repo）
        per_page: 每页结果数 (默认 30, 最大 100)
        page: 页码

    Returns:
        JSON 格式的分支列表
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/branches",
            params={"per_page": min(per_page, 100), "page": page},
        )

        branches = []
        for item in data:
            branches.append({
                "name": item.get("name"),
                "protected": item.get("protected"),
                "sha": item.get("commit", {}).get("sha", "")[:7],
            })

        return json.dumps(
            {
                "success": True,
                "repo": repo,
                "total_returned": len(branches),
                "branches": branches,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_tags(
    repo: str,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """
    获取 GitHub 仓库的标签列表。

    Args:
        repo: 仓库名称（格式: owner/repo）
        per_page: 每页结果数 (默认 30, 最大 100)
        page: 页码

    Returns:
        JSON 格式的标签列表
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/tags",
            params={"per_page": min(per_page, 100), "page": page},
        )

        tags = []
        for item in data:
            tags.append({
                "name": item.get("name"),
                "sha": item.get("commit", {}).get("sha", "")[:7],
                "zipball_url": item.get("zipball_url"),
                "tarball_url": item.get("tarball_url"),
            })

        return json.dumps(
            {
                "success": True,
                "repo": repo,
                "total_returned": len(tags),
                "tags": tags,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_get_readme(
    repo: str,
    ref: str = "main",
) -> str:
    """
    获取 GitHub 仓库的 README 文件内容。

    Args:
        repo: 仓库名称（格式: owner/repo）
        ref: 分支名、tag 或 commit SHA (默认: "main")

    Returns:
        README 文件的内容
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(
            f"/repos/{repo}/readme",
            params={"ref": ref},
        )

        content = data.get("content", "")
        encoding = data.get("encoding", "")

        if encoding == "base64":
            try:
                decoded_content = base64.b64decode(content).decode("utf-8")
            except Exception:
                decoded_content = "[Binary file - cannot decode as text]"
        else:
            decoded_content = content

        return json.dumps(
            {
                "success": True,
                "name": data.get("name"),
                "path": data.get("path"),
                "html_url": data.get("html_url"),
                "content": decoded_content,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


@mcp.tool()
async def github_list_languages(
    repo: str,
) -> str:
    """
    获取 GitHub 仓库使用的编程语言及其代码行数。

    Args:
        repo: 仓库名称（格式: owner/repo）

    Returns:
        JSON 格式的语言统计，键为语言名，值为字节数
    """
    if not repo:
        return json.dumps(
            {"success": False, "error": "'repo' is required"},
            ensure_ascii=False,
        )

    try:
        data = await _make_github_request(f"/repos/{repo}/languages")

        return json.dumps(
            {
                "success": True,
                "repo": repo,
                "languages": data,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return _format_error(e)


if __name__ == "__main__":
    mcp.run()
