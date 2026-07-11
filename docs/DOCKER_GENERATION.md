# Docker Generation

When a repository does not provide a usable Dockerfile, SecureWise can generate a temporary
one inside the scan workspace.

## Rules

- Do not overwrite repository files.
- Use the detected runtime version where known.
- Copy dependency manifests before source code when practical.
- Install only what is needed to run the app.
- Expose the detected candidate port.
- Use the detected start command.
- Keep the container non-root where feasible.

## Supported templates

- Python
- Node.js
- Go
- PHP
- Ruby

## What SecureWise does not assume

- that every Python app uses `requirements.txt`
- that every Node app uses `npm`
- that every service listens on port 8000
- that every repo is a web app

