# workflows

GitHub Actions reutilizáveis (`workflow_call`) do Pegasus TMS. Os microsserviços chamam estes workflows a partir do próprio `.github/workflows/deploy.yml`, sempre apontando para `@main`.

## Pipeline dos serviços

| Workflow | Estágio | O que faz |
|---|---|---|
| `build-push.yml` | 1 | `mvn -B clean verify -DexcludedGroups=integration` (Java 25, dependências do GitHub Packages) e build `linux/amd64` da imagem, publicada no ECR `pegasus/<service-name>` com a tag `<aaaammdd>-<sha>-<env>` e `latest`. O token do GitHub Packages entra no Docker como secret do BuildKit (`gh_token`). Saídas: `version` e `image`. |
| `deploy-vps.yml` | 2 (dev) | Ambiente dev: via SSH, faz login no ECR na VPS (o token sai do runner), grava `<SERVICO>_TAG` no `.env` do compose e sobe só o serviço com `docker compose -f docker-compose.vps.yml up -d --no-deps`. A troca do `.env` roda sob `flock`, com backup rotativo (`.env.bak.1..5`) e aborta se alguma variável fosse sumir. Depois espera o container ficar `healthy` (`health-timeout`, padrão 300 s; `0` desliga). |
| `deploy-aws.yml` | 2 (prod) | Registra nova revisão da task definition com a imagem (e `APP_VERSION` / `GIT_COMMIT_SHA`) e atualiza o service `pegasus-<env>-<service-name>` no cluster `pegasus-<env>-cluster`; espera estabilizar quando `desired_count > 0`. |
| `release.yml` | 3 | Cria tag e GitHub Release: `<timestamp>-<sha>` em `main`, `<timestamp>-<sha>-rc` (pre-release) nas demais branches. |

O ambiente é derivado da branch: `main` → prod (AWS), qualquer outra → dev (VPS).

Caller típico de um serviço (push em `develop` faz deploy na VPS; push em `main`, na AWS):

```yaml
on:
  push:
    branches: [develop, main]
  workflow_dispatch:

permissions:
  contents: write
  packages: read

jobs:
  build:
    uses: pegasustms/workflows/.github/workflows/build-push.yml@main
    with:
      service-name: meu-service
    secrets: inherit

  deploy-vps:
    needs: build
    if: github.ref_name != 'main'
    uses: pegasustms/workflows/.github/workflows/deploy-vps.yml@main
    with:
      service-name: meu-service
      image: ${{ needs.build.outputs.image }}
      version: ${{ needs.build.outputs.version }}
    secrets: inherit

  deploy-aws:
    needs: build
    if: github.ref_name == 'main'
    uses: pegasustms/workflows/.github/workflows/deploy-aws.yml@main
    with:
      service-name: meu-service
      image: ${{ needs.build.outputs.image }}
      version: ${{ needs.build.outputs.version }}
    secrets: inherit

  release:
    needs: [build, deploy-vps, deploy-aws]
    if: ${{ !cancelled() && needs.build.result == 'success' && (needs.deploy-vps.result == 'success' || needs.deploy-aws.result == 'success') }}
    uses: pegasustms/workflows/.github/workflows/release.yml@main
    with:
      service-name: meu-service
      display-name: Meu Service
      image: ${{ needs.build.outputs.image }}
      version: ${{ needs.build.outputs.version }}
    secrets: inherit
```

Com `secrets: inherit`, o repositório (ou a organização) precisa ter: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `PACKAGES_TOKEN` (opcional; sem ele usa o `GITHUB_TOKEN`), `VPS_HOST`, `VPS_USER` e `VPS_SSH_KEY`; e a variável `AWS_REGION`. Os jobs usam os environments `dev` e `prod` do GitHub.

O `service-name` tem de ser igual ao nome do repositório ECR, ao do service no `docker-compose.vps.yml` e ao do container na task definition do ECS.

## Operação na AWS

| Workflow | O que faz |
|---|---|
| `service-toggle.yml` | Sobe (`up`), desce (`down`) ou reinicia (`restart`) um service ECS ou todos (`all`) num ambiente |
| `datadog-collector.yml` | `up` / `down` / `restart` do datadog-collector compartilhado |
| `smoke-test.yml` | Chama `/actuator/health` de um service ou de todos e falha se não estiver `UP` |
| `terraform-plan.yml` / `terraform-apply.yml` | Plan (comentado no PR) e apply do Terraform a partir de um secret `TF_VARS_TFVARS`. O repositório `terraform` usa hoje workflow próprio, não estes. |

## Legado

- `deploy-service.yml`: build e deploy no ECS num único job (anterior ao pipeline acima).
- `build-and-push-gcp.yml` e `deploy-service-gcp.yml`: Artifact Registry / Cloud Run, da época do GCP.
- `templates/`: callers de exemplo dessa primeira versão; não refletem o pipeline atual.
