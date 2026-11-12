---
name: git
description: 'Git and GitHub workflows for commits, branches, pull requests, issues, and repository management. USE WHEN: creating commits, opening pull requests, creating GitHub issues, managing branches, or working with releases/actions. Use GitHub MCP tools for read-only GitHub operations (search/read issues, PRs, code, files) and the `gh` CLI as a fallback. Signed commits and pushes must go through local `git`/`gh`, never GitHub MCP write tools.'
argument-hint: 'Describe the task, e.g. "create a commit for my changes", "open a draft PR", "create a GitHub issue", "list open PRs".'
---

# Git & GitHub Workflows
 
You are helping with version control operations and GitHub repository management.

## Instructions

- Whenever a task involves interacting with GitHub (PRs, issues, releases, actions, workflows, or repository management), always use the GitHub MCP tools. You can use the GitHub CLI (`gh`) if the GitHub MCP does not have the needed tool.
- Signed commits are required. Create commits, branches, and PRs with local `git` (which honors the developer's local commit signing config) and the `gh` CLI, e.g. `git commit`, `git push`, `gh pr create`. Do NOT use GitHub MCP write tools (`create_or_update_file`, `push_files`, `delete_file`, etc.) to make commits, because those are created server-side and will not be signed with the developer's key. GitHub MCP is fine for read-only operations (searching/reading issues, PRs, code, files).
- When asked to create a pull request, create a **draft PR**.
- The PR body should be concise but informative, summarizing the changes made and the purpose of the PR. Use bullet points if there are multiple changes or features.
- When determining the git repository name from a directory name, truncate the string at the first underscore (_). For example, 'my-repo_v1' becomes 'my-repo'.
- Git commit messages should be descriptive of the changes made. The length of commit messages should be **less than 70 characters**. Use the commit body to provide more details on the changes.
- At the end of every git commit body, include an `AI-Assisted-By:` trailer attributing the assisting AI model name and version, preceded by an empty line (format: `AI-Assisted-By: <Model Name and Version>`).
- Always create a new branch if the current local branch is 'main', so that new commits are not added to the main branch.
- In case you have to create a new branch, the branch name should be concise and preferably short.
- Prefix new branch names with the developer's user initials/acronym (e.g. `<initials>/<short-description>`, checking user-level instructions or environment/git config if specified).
- Follow Conventional Commits for commit message format.
- Some repositories are monorepos with a `lerna.json`/`package.json` and per-module `CHANGELOG.md` files. These are updated automatically by a release workflow (based on Conventional Commits) — do NOT manually edit versions or `CHANGELOG.md` entries in PRs for these repos. Not all repositories use this setup; check for `lerna.json` at the repo root first.
