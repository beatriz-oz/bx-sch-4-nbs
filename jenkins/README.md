# Local Jenkins

A Jenkins in Docker that checks both repositories on demand:

| Job | Repository | What it checks |
|---|---|---|
| `bx-sch-4-nbs` | this one ([Jenkinsfile](../Jenkinsfile)) | ruff, ty, migrations (up, down, up + `alembic check`), demo data and every `try_*` script, against a throwaway MySQL 8.0 and Mailpit |
| `bx-sch-4-nbs-front` | [bx-sch-4-nbs-front](https://github.com/beatriz-oz/bx-sch-4-nbs-front) (its `Jenkinsfile`) | `npm ci`, complete Portuguese translations, unit tests, build of `/en` and `/pt-PT` |

Jenkins is configured as code ([casc.yaml](casc.yaml)): the admin user and both jobs exist from the first start, with no setup wizard.

## Start

```bash
cp .env.example .env    # then choose JENKINS_ADMIN_PASSWORD in .env (never committed)
docker compose up -d --build
```

Open <http://localhost:8080> and log in as `admin` with that password.

## Run a pipeline

Open a job → **Build with Parameters** → choose the branch (`develop`, `uat` or `main`) → **Build**.
Jenkins clones the branch from GitHub: push first what you want checked.

`DEPLOY_BENCH` is a placeholder: the bench deploy comes with the Docker deploy, so for now it stops the build on purpose.

## How it works

- The image ([Dockerfile](Dockerfile)) adds uv, Node 24 and the Docker command line to the official Jenkins (Java 21).
- The host's Docker socket is mounted, so a back end build starts its own MySQL and Mailpit containers on the `nbs-ci` network and removes them at the end, whatever happens.
- Every build writes fresh secrets to a temporary `.env`: no real key ever reaches Jenkins.
- Jobs, history and the uv/npm caches live in the `jenkins_home` volume.

## Stop / remove

```bash
docker compose down        # stop (keeps jobs and history)
docker compose down -v     # also delete the jenkins_home volume
```
