"""
unificar_verbo.py — Unifica as duas transcrições de verbo num único resumo

Lógica:
  1. Lê a transcrição original (aula1_verbo_transcricao.txt)
  2. Lê a transcrição do complemento (aula_verbo_transcricao.txt)
  3. Concatena as duas como uma única aula longa
  4. Envia para Claude gerar um resumo unificado e coerente
  5. Salva em: transcricoes/verbo_unificado_resumo.txt
             transcricoes/verbo_unificado_resumo_html.txt

Uso:
    python src/unificar_verbo.py
"""

import os
import sys
from pathlib import Path
import anthropic

PASTA_TRANSCRICOES = Path("transcricoes")
CHAVE_API_ENV      = "ANTHROPIC_API_KEY"
MODELO_CLAUDE      = "claude-haiku-4-5-20251001"
MAX_TOKENS         = 8192

TRANSCRICAO_ORIGINAL   = PASTA_TRANSCRICOES / "aula1_verbo_transcricao.txt"
TRANSCRICAO_COMPLEMENTO = PASTA_TRANSCRICOES / "aula_verbo_transcricao.txt"
SAIDA_RESUMO           = PASTA_TRANSCRICOES / "verbo_unificado_resumo.txt"
SAIDA_HTML             = PASTA_TRANSCRICOES / "verbo_unificado_resumo_html.txt"


def carregar_chave_api() -> str:
    chave = os.environ.get(CHAVE_API_ENV, "").strip()
    if chave:
        return chave
    arquivo = Path("api_claude.txt")
    if arquivo.exists():
        chave = arquivo.read_text(encoding="utf-8").strip()
        if chave.startswith("sk-ant-"):
            return chave
    print("❌ Chave API não encontrada.")
    print("   Crie api_claude.txt com sua chave sk-ant-...")
    sys.exit(1)


def carregar_transcricao(caminho: Path) -> str:
    if not caminho.exists():
        print(f"❌ Arquivo não encontrado: {caminho}")
        print("   Execute primeiro: python src/transcrever.py resumo/Portugues/aula_verbo.mp4")
        sys.exit(1)
    texto = caminho.read_text(encoding="utf-8").strip()
    print(f"✅ Carregado: {caminho} ({len(texto.split())} palavras)")
    return texto


def gerar_resumo_unificado(transcricao1: str, transcricao2: str, chave_api: str) -> str:
    print("\n🤖 Gerando resumo unificado com Claude API...")

    # Limita cada transcrição para evitar estouro de contexto
    MAX_CHARS = 40_000
    if len(transcricao1) > MAX_CHARS:
        print(f"   ⚠️  Transcrição 1 truncada para {MAX_CHARS} chars")
        transcricao1 = transcricao1[:MAX_CHARS] + "\n\n[... continua na parte 2 ...]"
    if len(transcricao2) > MAX_CHARS:
        print(f"   ⚠️  Transcrição 2 truncada para {MAX_CHARS} chars")
        transcricao2 = transcricao2[:MAX_CHARS] + "\n\n[... fim do complemento ...]"

    prompt = f"""Você é uma professora especialista em concursos públicos brasileiros, banca CESGRANRIO.

Abaixo estão DUAS transcrições de aulas sobre VERBOS. A segunda é um complemento que aprofunda ou expande a primeira.
Crie um RESUMO DE ESTUDO UNIFICADO e completo, como se fossem uma única aula.

INSTRUÇÕES:
- Integre os conteúdos das duas aulas de forma coerente (sem repetições desnecessárias)
- Organize em seções com títulos claros
- Liste todas as REGRAS e CONCEITOS em tópicos curtos
- Inclua EXEMPLOS PRÁTICOS das duas aulas
- Destaque os pontos que mais caem nas provas CESGRANRIO
- Use linguagem simples e direta
- No final, faça um RESUMO EM ÁUDIO: frases curtas, pausas marcadas com [pausa], como se fosse um roteiro para ouvir no celular
- Escreva tudo em português

PARTE 1 — AULA ORIGINAL:
{transcricao1}

---

PARTE 2 — COMPLEMENTO:
{transcricao2}"""

    cliente = anthropic.Anthropic(api_key=chave_api)
    resposta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )
    return resposta.content[0].text


def salvar_resumo(resumo: str) -> None:
    PASTA_TRANSCRICOES.mkdir(exist_ok=True)

    # Salva texto puro
    SAIDA_RESUMO.write_text(resumo, encoding="utf-8")
    print(f"✅ Resumo unificado salvo em: {SAIDA_RESUMO}")

    # Gera snippet HTML
    linhas = resumo.split("\n")
    html_linhas = []
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("# "):
            html_linhas.append(f"<h2>{linha[2:]}</h2>")
        elif linha.startswith("## "):
            html_linhas.append(f"<h3>{linha[3:]}</h3>")
        elif linha.startswith("- ") or linha.startswith("• "):
            html_linhas.append(f"<li>{linha[2:]}</li>")
        elif linha.startswith("**") and linha.endswith("**"):
            html_linhas.append(f"<strong>{linha[2:-2]}</strong>")
        else:
            html_linhas.append(f"<p>{linha}</p>")

    snippet = f"""
<!-- ═══ RESUMO UNIFICADO: VERBOS ═══ -->
<div class="semana-bloco" id="resumo-verbos">
  <h2 class="semana-titulo">📖 Verbos — Resumo Completo (Aula + Complemento)</h2>
  <div class="resumo-corpo">
    {''.join(html_linhas)}
  </div>
</div>
"""
    SAIDA_HTML.write_text(snippet, encoding="utf-8")
    print(f"✅ Snippet HTML salvo em: {SAIDA_HTML}")
    print("   → Copie o conteúdo para revisao.html")


def main():
    print(f"\n{'='*60}")
    print("  UNIFICADOR DE TRANSCRIÇÕES — VERBOS")
    print(f"{'='*60}\n")

    # Verifica se o complemento já foi transcrito
    if not TRANSCRICAO_COMPLEMENTO.exists():
        print("⚠️  Transcrição do complemento ainda não existe.")
        print(f"   Arquivo esperado: {TRANSCRICAO_COMPLEMENTO}")
        print("\n   Execute primeiro:")
        print("   python src/transcrever.py resumo/Portugues/aula_verbo.mp4")
        sys.exit(1)

    print("📂 Carregando transcrições...")
    texto1 = carregar_transcricao(TRANSCRICAO_ORIGINAL)
    texto2 = carregar_transcricao(TRANSCRICAO_COMPLEMENTO)

    chave_api = carregar_chave_api()
    resumo = gerar_resumo_unificado(texto1, texto2, chave_api)
    salvar_resumo(resumo)

    print(f"\n{'='*60}")
    print("  CONCLUÍDO!")
    print(f"{'='*60}")
    print(f"\n  📄 {SAIDA_RESUMO}")
    print(f"  📄 {SAIDA_HTML}")


if __name__ == "__main__":
    main()
