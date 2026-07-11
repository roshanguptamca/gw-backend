# Application Discovery

SecureWise discovery reads repository files only. It never imports or executes target code.

## Inputs

- README files
- `Dockerfile`
- `docker-compose.yml` / `compose.yaml`
- Python packaging files
- JavaScript/TypeScript package manifests
- Java build files
- Go modules
- PHP Composer files
- Ruby Bundler files
- source entrypoints
- environment example files

## Outputs

Discovery produces an application run plan with:

- detected languages and frameworks
- package manager
- dependency files
- build and start commands
- candidate ports
- health candidates
- required services
- confidence score
- blocking reasons and warnings

## Detection priorities

README and explicit project configuration take priority over generic heuristics.
If a repository gives a clear start command or documented runtime path, SecureWise should use that first.

## Supported examples

- Django via `manage.py` or packaged `src/.../settings.py`
- FastAPI and Flask via import markers and ASGI/WSGI entrypoints
- Express, NestJS, Next.js, React, and Vite via `package.json`
- Spring Boot via Maven or Gradle
- Go services via `go.mod` and `main.go`
- Laravel via Composer
- Rails and Rack apps via Gemfile/config files

