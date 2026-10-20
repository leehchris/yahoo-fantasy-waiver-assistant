# Free Yahoo-to-ChatGPT private data bridge

## Architecture

The existing read-only Yahoo client remains on the user's Windows machine, with OAuth secrets under ignored local paths. A PowerShell script refreshes reports and pushes only generated data to a **separate GitHub repository that it verifies is private**. ChatGPT's installed GitHub integration can then fetch authorized files on request.

Do **not** publish Yahoo tokens, `.env`, browser cookies, or private league data to the existing public code repository.

## One-time setup

1. Install the free GitHub CLI from https://cli.github.com/ and sign in with `gh auth login`.
2. Create a **new, empty, private** repository on GitHub, e.g., `yahoo-fantasy-private-data`. Confirm its visibility is Private.
3. Clone it into a *separate* directory, e.g., `C:\Users\<you>\Documents\yahoo-fantasy-private-data`. Do not create it inside the public repository.
4. On ChatGPT's connected GitHub app configuration, allow access to that private repository. New repositories may take several minutes to appear. Test that ChatGPT can fetch `yahoo/latest-report.md` after the first publishing run.
5. From the existing public code repo root, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish-private-yahoo.ps1 -PrivateRepoPath "C:\Users\<you>\Documents\yahoo-fantasy-private-data"
```

The script refuses to publish unless the GitHub CLI confirms the destination is private. It runs the existing Yahoo refresh, copies the most recent matching report files and snapshot into the private clone, commits the changes, then pushes. Existing OAuth credentials never leave the local Yahoo application. **Private data does leave the PC and is stored in GitHub and may be accessed by ChatGPT**.

## Automation

After confirming an interactive run works, schedule this exact command with Windows Task Scheduler at the desired interval (e.g., once daily, and before waivers). Choose **Run only when user is logged on** unless Git and Yahoo authentication work unattended. The machine must be powered on and connected. Set retry behavior and check Task Scheduler history. Do not schedule until the privacy and GitHub read tests pass.

## ChatGPT usage

Ask: "Read yahoo/latest-report.md and yahoo/latest-report.json from my private yahoo-fantasy-private-data GitHub repo. Check the capture timestamp, analyze injuries, roster holes, eligible additions, FAAB and add/drop priority. If data is older than 24 hours, flag it as stale instead of claiming it is live."

GitHub's connected app supports authorized repository reads in supported ChatGPT experiences; access to a newly created private repository must be explicitly enabled and verified. This is a *snapshot bridge*, **not** live MCP or direct Yahoo API access.

## Safety and operating considerations

- The public code repository never contains league snapshots or secrets.
- The private GitHub repository should contain *data only*, not authentication tokens.
- Private Git history retains earlier snapshots; deleting a current file does not erase older commits.
- `fantasy-update-*.json` and snapshots can be large; read tool size limits may constrain downstream analysis. Consider compact per-topic exports later if necessary.
- The script intentionally does not submit adds, drops, waiver claims, or trades.
- Private GitHub repositories have a free tier. No paid GitHub Actions or hosting is required because the publisher runs locally.
- Always inspect generated snapshot content before the **first** upload; revoke/delete any accidentally included secrets before continuing.
