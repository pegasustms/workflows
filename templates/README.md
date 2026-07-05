# Templates de Caller — Copia & cola

Cada repo do Pegasus (services + terraform + frontend) precisa de 1-2 callers que
**invocam** os workflows reusables deste repo (`pegasustms/workflows`).

## Templates disponíveis

| Template | Para que tipo de repo | O que faz |
|---|---|---|
| [`service-on-push.yml`](service-on-push.yml) | Cada microsserviço Java (16) | Build + push ECR + deploy quando push em main |
| [`service-toggle.yml`](service-toggle.yml) | Cada microsserviço (opcional) | Botão "subir/descer" service no GitHub UI |
| [`service-smoke.yml`](service-smoke.yml) | Cada microsserviço (opcional) | Health check após deploy |
| [`terraform-pr-plan.yml`](terraform-pr-plan.yml) | Repo `pegasustms/terraform` | Roda plan em PRs e comenta resultado |
| [`terraform-main-apply.yml`](terraform-main-apply.yml) | Repo `pegasustms/terraform` | Apply quando merge em main |
| [`fleet-toggle.yml`](fleet-toggle.yml) | Repo `pegasustms/workflows` (este) | Manual: subir/descer service por nome via UI |
| [`fleet-smoke-cron.yml`](fleet-smoke-cron.yml) | Repo `pegasustms/workflows` (este) | Cron diário: smoke em todos services |

## Como aplicar

### Para cada microsserviço (16×)

Copiar para `<service>/.github/workflows/deploy.yml`:

```yaml
# Copiado de pegasustms/workflows/templates/service-on-push.yml
# Substituir 'tenant-service' → nome real do service.
```

### Para o terraform

Copiar para `terraform/.github/workflows/{plan,apply}.yml` os dois arquivos.

### Secrets necessários nos repos

Em **Settings → Secrets and variables → Actions** de cada repo (ou em Organization Secrets):

| Secret | Onde |
|---|---|
| `AWS_ACCESS_KEY_ID` | Todos os repos que tocam AWS |
| `AWS_SECRET_ACCESS_KEY` | Todos os repos que tocam AWS |
| `WORKFLOW_TOKEN` | PAT com `repo` scope para acessar deps GitHub Packages (commons) |
| `TF_VARS_TFVARS` | Só no repo `terraform` — conteúdo completo do terraform.tfvars |

### Variables necessárias (não-sensíveis)

| Variable | Onde | Valor |
|---|---|---|
| `AWS_REGION` | Organization variables ou cada repo | `us-east-1` |

### Environments do GitHub (Settings → Environments)

Criar em cada repo (services + terraform):
- `dev` — sem required reviewers (auto deploy)
- `stg` — required reviewers (opcional)
- `prod` — required reviewers obrigatório, com regra de proteção `branches: main`
