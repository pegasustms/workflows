#!/usr/bin/env python3
"""Normaliza uma árvore de docs: nomes kebab-case + frontmatter inferido.

Uso: normalizar.py <raiz> [--servico <nome>] [--datas-git <repo>]
  --servico     força servicos: [<nome>] (docs de um repositório de serviço)
  --datas-git   usa a data do último commit do arquivo em <repo> (senão mtime)
Idempotente: arquivo que já tem frontmatter não é tocado.
"""
import argparse
import datetime as dt
import re
import subprocess
import unicodedata
from pathlib import Path

SERVICOS = ["api-gateway", "tenant-service", "company-service", "master-data", "conhecimento-service",
            "emissor-service", "fiscal-service", "averbacao-service", "documentos-service",
            "manifestos-service", "financeiro-service", "contabilidade-service", "comercial-service",
            "coletas-service", "mobile-bff-service", "relatorio-service", "rastreamento-service",
            "notificacao-service", "escrituracao-service", "ciot-service", "parceiras-service",
            "marketplaces-service", "commons", "frontend", "admin-frontend", "mobile", "landing-page",
            "terraform", "workflows"]
LIVRES = {"README.md", "SPEC.md", "CHANGELOG.md"}
TEXTO = {".md", ".txt", ".json", ".html", ".puml"}


def kebab(nome: str) -> str:
    if nome in LIVRES:
        return nome
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", s)
    s = re.sub(r"[\s_]+", "-", s.lower())
    s = re.sub(r"[^a-z0-9.-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def renomear(raiz: Path) -> dict:
    trocas = {}
    for p in sorted(raiz.rglob("*"), key=lambda x: -len(x.parts)):
        if any(part.startswith(".") or part == "design" for part in p.relative_to(raiz).parts):
            continue
        novo = kebab(p.name)
        if novo != p.name:
            trocas[p.name] = novo
            alvo = p.with_name(novo)
            tmp = p.with_name(novo + ".__tmp__")
            p.rename(tmp)
            tmp.rename(alvo)
    if trocas:
        for f in raiz.rglob("*"):
            if f.is_file() and f.suffix in TEXTO:
                t = f.read_text(encoding="utf-8", errors="replace")
                n = t
                for velho, novo in sorted(trocas.items(), key=lambda kv: -len(kv[0])):
                    n = re.sub(r"(?<![\w.-])" + re.escape(velho) + r"(?![\w-])", novo, n)
                if n != t:
                    f.write_text(n, encoding="utf-8")
    return trocas


def tipo_de(rel: Path) -> str:
    partes, nome = rel.parts, rel.stem
    if "adr" in partes:
        return "adr"
    if partes[0] == "templates":
        return "template"
    if "postmortems" in partes:
        return "postmortem"
    if "issues" in partes:
        return "issue"
    if nome.startswith("runbook"):
        return "runbook"
    if nome.startswith("layout"):
        return "layout"
    if nome.startswith("pesquisa"):
        return "pesquisa"
    if nome.startswith("estado-atual"):
        return "estado-atual"
    if "design" in partes:
        return "design"
    if partes[0] == "tasks" or "roadmap" in nome or "backlog" in nome:
        return "roadmap"
    if partes[0] in ("operations", "contributing"):
        return "guia"
    if partes[0] in ("product", "domain", "architecture") or nome in ("contratos", "mapeamento-dados"):
        return "referencia"
    return "spec"


STATUS_RE = re.compile(r"\*\*(?i:status):?\*\*\s*:?\s*\|?\s*([^|\n]+)|^\s*[-*>]*\s*Status\s*:\s*([^\n]+)", re.M)


def status_de(texto: str, tipo: str):
    cabecalho = re.sub(r"```.*?```", "", texto, flags=re.S)  # payloads de exemplo têm campo status
    m = STATUS_RE.search("\n".join(cabecalho.splitlines()[:60]))
    s = (m.group(1) or m.group(2)).lower()[:40] if m else ""
    for chave, val in [(r"cancelad|cancelled|canceled", "cancelado"), (r"obsolet|supersed|substitu|deprecad", "obsoleto"),
                       (r"paus|⏸", "pausado"), (r"in progress|in review|andamento|\bwip\b", "em-andamento"),
                       (r"implement|conclu|entregue|done|mergead", "implementado"),
                       (r"approv|aprovad|accept|aceit", "approved"), (r"draft|propost|rascunho|proposed", "draft")]:
        if s and re.search(chave, s):
            return val
    return None


def titulo_de(texto: str, rel: Path) -> str:
    m = re.search(r"^#\s+(.+)$", texto, re.M)
    t = m.group(1).strip() if m else rel.stem.replace("-", " ").capitalize()
    t = re.sub(r"^(feature spec|spec)\s*[—:-]\s*", "", t, flags=re.I)
    if not m:
        c = re.search(r"título:\s*([^>]+?)\s*-->", texto)
        t = c.group(1) if c else t
    return t.replace('"', "'")


def servicos_de(texto: str, forcado):
    if forcado:
        return [forcado]
    achados = [s for s in SERVICOS if re.search(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", texto)]
    return achados


def data_de(f: Path, repo):
    if repo:
        r = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%cs", "--", str(f)],
                           capture_output=True, text=True)
        if r.stdout.strip():
            return r.stdout.strip()
    return dt.date.fromtimestamp(f.stat().st_mtime).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raiz")
    ap.add_argument("--servico")
    ap.add_argument("--datas-git")
    a = ap.parse_args()
    raiz = Path(a.raiz).resolve()

    # datas antes de renomear (o git log segue o caminho antigo)
    datas = {raiz.joinpath(*[kebab(x) for x in f.relative_to(raiz).parts]): data_de(f, a.datas_git)
             for f in raiz.rglob("*.md")}
    trocas = renomear(raiz)

    status_feature = {}
    mds = sorted(raiz.rglob("*.md"))
    for f in mds:  # primeiro as specs, para as issues herdarem o status
        if f.name == "spec.md":
            status_feature[f.parent] = status_de(f.read_text(encoding="utf-8"), "spec")

    for f in mds:
        if f.name == "README.md":
            continue
        texto = f.read_text(encoding="utf-8")
        if texto.startswith("---\n"):
            continue
        rel = f.relative_to(raiz)
        tipo = "spec" if a.servico and f.name == "SPEC.md" else tipo_de(rel)
        st = status_de(texto, tipo)
        if not st and tipo == "issue":
            st = status_feature.get(f.parent.parent)
        if not st:  # sem status declarado: doc de serviço descreve o que existe; feature spec nasce draft
            st = "draft" if tipo in ("spec", "issue", "pesquisa") and not a.servico else "vigente"
        if tipo == "adr" and st == "vigente":
            st = "approved"
        servs = servicos_de(texto, a.servico)
        fm = (f"---\ntitulo: \"{titulo_de(texto, rel)}\"\ntipo: {tipo}\nstatus: {st}\n"
              f"servicos: [{', '.join(servs)}]\natualizado: {datas.get(f) or data_de(f, None)}\n---\n\n")
        f.write_text(fm + texto, encoding="utf-8")

    for velho, novo in trocas.items():
        print(f"renomeado: {velho} -> {novo}")


if __name__ == "__main__":
    main()
