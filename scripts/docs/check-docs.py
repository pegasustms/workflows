#!/usr/bin/env python3
"""Valida a normalização da documentação do Pegasus.

Uso: check-docs.py <raiz-dos-docs> [--allowlist arquivo]
     (allowlist padrão: <raiz>/.docs-allowlist; os fictícios de FICTICIOS valem sempre)

Regras (ver NORMALIZACAO.md):
  1. Nome de arquivo/pasta em minúsculas, ASCII, kebab-case ([a-z0-9._-]); exceções: README.md, SPEC.md, CHANGELOG.md
     e o conteúdo de pastas design/ (exportado pela ferramenta de design).
  2. Todo .md (menos README.md) abre com frontmatter YAML com titulo, tipo, status, servicos, atualizado.
  3. Sem CNPJ/CPF com dígito verificador válido fora da allowlist (dados reais de cliente não entram).
  4. Sem planilhas, dumps, .env ou arquivos acima de 2 MB.
  5. Links relativos apontam para arquivos que existem.
Sem dependências externas (roda em qualquer runner com Python 3.9+).
Guia completo: contributing/normalizacao-docs.md no repositório specs.
"""
import argparse
import re
import sys
from pathlib import Path

# CNPJs fictícios (DV válido) para usar nos exemplos no lugar de dado de cliente
FICTICIOS = {"11222333000181", "11222333000262", "44555666000181", "77888999000181",
             "12121212000106", "34343434000106", "56565656000106"}
TIPOS = {"spec", "adr", "guia", "runbook", "layout", "pesquisa", "issue", "roadmap",
         "template", "referencia", "postmortem", "indice", "design", "estado-atual"}
STATUS = {"draft", "approved", "em-andamento", "implementado", "pausado", "cancelado", "obsoleto", "vigente"}
OBRIGATORIOS = ("titulo", "tipo", "status", "servicos", "atualizado")
NOMES_LIVRES = {"README.md", "SPEC.md", "CHANGELOG.md"}
EXT_PROIBIDAS = {".csv", ".xlsx", ".xls", ".ods", ".env", ".sql", ".dump", ".bak", ".p12", ".pfx", ".pem", ".key"}
LIMITE_BYTES = 2 * 1024 * 1024
TEXTO = {".md", ".txt", ".json", ".html", ".puml", ".yml", ".yaml", ".xml"}

NOME_OK = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CNPJ = re.compile(r"(?<![\d/])(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?![\d/])")
CPF = re.compile(r"(?<![\d.])(\d{3}\.\d{3}\.\d{3}-\d{2})(?![\d])|(?i:\bcpf\D{0,6})(\d{11})(?!\d)")
LINK = re.compile(r"\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def dv_cnpj(base: str) -> str:
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(d) * p for d, p in zip(base, pesos))
    d1 = 0 if s % 11 < 2 else 11 - s % 11
    s = sum(int(d) * p for d, p in zip(base + str(d1), [6] + pesos))
    d2 = 0 if s % 11 < 2 else 11 - s % 11
    return f"{d1}{d2}"


def dv_cpf(base: str) -> str:
    s = sum(int(d) * p for d, p in zip(base, range(10, 1, -1)))
    d1 = (s * 10 % 11) % 10
    s = sum(int(d) * p for d, p in zip(base + str(d1), range(11, 1, -1)))
    return f"{d1}{(s * 10 % 11) % 10}"


def cnpj_valido(n: str) -> bool:
    return len(n) == 14 and len(set(n)) > 1 and dv_cnpj(n[:12]) == n[12:]


def cpf_valido(n: str) -> bool:
    return len(n) == 11 and len(set(n)) > 1 and dv_cpf(n[:9]) == n[9:]


def frontmatter(texto: str):
    if not texto.startswith("---\n"):
        return None
    fim = texto.find("\n---\n", 4)
    if fim < 0:
        return None
    campos = {}
    for linha in texto[4:fim].splitlines():
        if ":" in linha and not linha.startswith((" ", "#")):
            k, v = linha.split(":", 1)
            campos[k.strip()] = v.strip()
    return campos


def checar(raiz: Path, allowlist: set) -> list:
    erros = []
    for f in sorted(raiz.rglob("*")):
        rel = f.relative_to(raiz)
        if any(p.startswith(".") for p in rel.parts):
            continue
        gerado = "design" in rel.parts[:-1]  # exportado pela ferramenta de design: mantém os nomes dela
        if f.name not in NOMES_LIVRES and not gerado and not NOME_OK.match(f.name):
            erros.append(f"{rel}: nome fora do padrão (minúsculas, ASCII, kebab-case)")
        if f.is_dir():
            continue
        if f.suffix.lower() in EXT_PROIBIDAS:
            erros.append(f"{rel}: extensão {f.suffix} não entra na documentação (dados ficam fora do git)")
        if f.stat().st_size > LIMITE_BYTES:
            erros.append(f"{rel}: maior que 2 MB")
        if f.suffix.lower() not in TEXTO:
            continue
        texto = f.read_text(encoding="utf-8", errors="replace")

        for i, linha in enumerate(texto.splitlines(), 1):
            for m in CNPJ.findall(linha):
                n = re.sub(r"\D", "", m)
                if cnpj_valido(n) and n not in allowlist:
                    erros.append(f"{rel}:{i}: CNPJ {n} parece real; use um fictício ou inclua na allowlist com justificativa")
            for a, b in CPF.findall(linha):
                n = re.sub(r"\D", "", a or b)
                if cpf_valido(n) and n not in allowlist:
                    erros.append(f"{rel}:{i}: CPF {n} parece real; use um fictício")

        if f.suffix != ".md":
            continue
        if f.name != "README.md":
            fm = frontmatter(texto)
            if fm is None:
                erros.append(f"{rel}: sem frontmatter YAML")
            else:
                for k in OBRIGATORIOS:
                    if not fm.get(k):
                        erros.append(f"{rel}: frontmatter sem '{k}'")
                if fm.get("tipo") and fm["tipo"] not in TIPOS:
                    erros.append(f"{rel}: tipo '{fm['tipo']}' fora de {sorted(TIPOS)}")
                if fm.get("status") and fm["status"] not in STATUS:
                    erros.append(f"{rel}: status '{fm['status']}' fora de {sorted(STATUS)}")
                if fm.get("atualizado") and not DATA.match(fm["atualizado"]):
                    erros.append(f"{rel}: atualizado deve ser AAAA-MM-DD")
                if fm.get("servicos") and not (fm["servicos"].startswith("[") and fm["servicos"].endswith("]")):
                    erros.append(f"{rel}: servicos deve ser lista [a, b]")

        sem_codigo = re.sub(r"```.*?```", "", texto, flags=re.S)
        for alvo in LINK.findall(sem_codigo):
            if re.match(r"^[a-z]+:", alvo) or alvo.startswith("#"):
                continue
            caminho = alvo.split("#")[0]
            if caminho and not (f.parent / caminho).exists():
                erros.append(f"{rel}: link quebrado -> {alvo}")
    return erros


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raiz")
    ap.add_argument("--allowlist", default=None)
    a = ap.parse_args()
    raiz = Path(a.raiz)
    allow = set(FICTICIOS)
    arq = Path(a.allowlist) if a.allowlist else raiz / ".docs-allowlist"
    if arq.exists():
        for linha in arq.read_text().splitlines():
            linha = linha.split("#")[0].strip()
            if linha:
                allow.add(re.sub(r"\D", "", linha))
    erros = checar(raiz, allow)
    for e in erros:
        print(f"::error::{e}" if "GITHUB_ACTIONS" in __import__("os").environ else e)
    print(f"{len(erros)} problema(s) em {raiz}")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
