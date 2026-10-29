#!/usr/bin/env python3
"""Cria ou atualiza o ruleset "Protecao develop/main" em todos os repos da org.

Idempotente: rodar de novo depois de mergear um caller (pr-check.yml, migrations.yml)
passa a exigir o check correspondente naquele repo.

Regras, nos branches padrao, develop e main:
  - nao pode apagar o branch nem dar force push;
  - mudanca so por PR (sem exigir aprovacao);
  - checks obrigatorios conforme os workflows presentes no branch padrao. Repo com o
    GitHub Actions desligado (ex.: template-service) nao exige check nenhum: os workflows
    sao copiados para os repos novos, mas nunca rodariam ali e travariam os PRs.
Bypass: so admin da org, e so dentro de um PR (push direto continua bloqueado).
Tambem liga "apagar branch no merge" no repo.

Uso: scripts/aplicar-rulesets.py [--dry-run] [repo ...]   (precisa do gh com admin)
"""
import json
import re
import subprocess
import sys

ORG = "pegasustms"
NOME = "Protecao develop/main"
GITHUB_ACTIONS = 15368  # integration_id do app GitHub Actions (evita check falsificado)

# Workflow caller -> checks que ele gera ("<job do caller> / <job do reusable>")
CHECKS = {
    "pr-check-maven.yml": ["build-test / Build & Test (Maven)", "build-test / gitleaks / Segredos (gitleaks)",
                           "build-test / docs / Normalização dos docs"],
    "pr-check-node.yml": ["check / Lint, tipos e build", "check / gitleaks / Segredos (gitleaks)",
                          "check / docs / Normalização dos docs"],
    "gitleaks.yml": ["gitleaks / Segredos (gitleaks)"],
    "check-docs.yml": ["docs / Normalização dos docs"],
    "check-migrations.yml": [
        "migrations / Migrations (estatica)",
        "migrations / Migrations (Postgres descartavel)",
    ],
}


def gh(*args, entrada=None):
    r = subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def dispara_em_pr(conteudo):
    """O bloco on: (ate a proxima chave de topo) tem pull_request. Reusable que so cita
    pull_request no script nao conta."""
    m = re.search(r"(?ms)^on:(.*?)(?=^\S)", conteudo + "\nfim:")
    return bool(m) and "pull_request" in m.group(1)


def actions_ligado(repo):
    return json.loads(gh("api", f"repos/{ORG}/{repo}/actions/permissions"))["enabled"]


def checks_do_repo(repo, branch):
    """Checks gerados pelos callers de PR (pull_request) presentes no branch."""
    if not actions_ligado(repo):
        return []
    try:
        arquivos = json.loads(gh("api", f"repos/{ORG}/{repo}/contents/.github/workflows?ref={branch}"))
    except RuntimeError:
        return []
    checks = []
    for a in arquivos:
        if not a["name"].endswith((".yml", ".yaml")):
            continue
        conteudo = gh("api", a["url"], "-H", "Accept: application/vnd.github.raw")
        if not dispara_em_pr(conteudo):
            continue
        for reusable, nomes in CHECKS.items():
            if f"/{reusable}@" in conteudo:
                checks += [c for c in nomes if c not in checks]
    return checks


def ruleset(checks):
    regras = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": False,
                "allowed_merge_methods": ["merge", "squash", "rebase"],
            },
        },
    ]
    if checks:
        regras.append({
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "do_not_enforce_on_create": False,
                "required_status_checks": [{"context": c, "integration_id": GITHUB_ACTIONS} for c in checks],
            },
        })
    return {
        "name": NOME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH", "refs/heads/develop", "refs/heads/main"], "exclude": []}},
        "bypass_actors": [{"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "pull_request"}],
        "rules": regras,
    }


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    repos = [a for a in args if a != "--dry-run"]
    todos = json.loads(gh("repo", "list", ORG, "--limit", "200", "--no-archived", "--json", "name,defaultBranchRef"))
    padrao = {r["name"]: r["defaultBranchRef"]["name"] for r in todos}
    for repo in repos or sorted(padrao):
        checks = checks_do_repo(repo, padrao[repo])
        corpo = json.dumps(ruleset(checks))
        existentes = json.loads(gh("api", f"repos/{ORG}/{repo}/rulesets"))
        atual = next((r for r in existentes if r["name"] == NOME), None)
        acao = "atualiza" if atual else "cria"
        if not dry:
            # Branch do PR some no merge (PR empilhado e redirecionado para a base pelo GitHub)
            gh("api", "-X", "PATCH", f"repos/{ORG}/{repo}", "-F", "delete_branch_on_merge=true")
            if atual:
                gh("api", "-X", "PUT", f"repos/{ORG}/{repo}/rulesets/{atual['id']}", "--input", "-", entrada=corpo)
            else:
                gh("api", "-X", "POST", f"repos/{ORG}/{repo}/rulesets", "--input", "-", entrada=corpo)
        print(f"{repo:28} {acao:9} checks: {', '.join(checks) or '-'}{'  (dry-run)' if dry else ''}")


if __name__ == "__main__":
    main()
