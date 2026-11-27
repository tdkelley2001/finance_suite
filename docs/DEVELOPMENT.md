# MoneyLab development workflow

## Development environments
GitHub is the source of truth. Use Codex Cloud from a browser or Codex in VS Code locally. Work on a dedicated branch and deliver a pull request. Changes that are only on a local disk or in a chat are not shared until committed and pushed.

The existing application is Streamlit-based. The React/FastAPI architecture is a planned migration, not part of the development-foundation milestone.

## Python setup
Use Python 3.11, consistent with `.devcontainer/devcontainer.json`.

Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Windows PowerShell:
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Run the existing app:
```bash
streamlit run app.py
```

The application uses Supabase for authenticated sessions and profile storage. A fresh development environment may require appropriately configured secrets or a strictly local development bypass. Baseline unit tests should not require actual Supabase credentials.

## Pull request checks
The GitHub Actions workflow performs Python compilation and the baseline unit tests. Future milestones should add more focused financial-reference, API, integration, and browser tests as the corresponding components are built.

## Review standards
- UI-only changes: functionality, responsive layout, accessibility.
- Data/persistence changes: schema compatibility, ownership, authentication and scenario isolation.
- Financial model changes: independent references, edge cases, timing conventions, reconciliation, reproducibility and methodological approval.
- Do not merge or deploy a change merely because CI passes.

## Cloud development reminders
Cloud environments may not have local environment variables, personal datasets, or running services. Keep setup reproducible and secrets out of Git; never use real user financial data as test fixtures. Pin changes in a PR and verify CI before review.
