"""Prompt templates for the AI enrichment step.

Prompts are versioned next to the code so changes are reviewable.  The model is
asked for a strict JSON object, in Brazilian Portuguese, grounded exclusively in
the resume and job description (no invented experience).
"""

from __future__ import annotations

import json

from app.analyzer.ai.base import AnalysisContext

PROMPT_VERSION = "2024-11-01"

MAX_RESUME_CHARS = 6_000
MAX_JOB_DESCRIPTION_CHARS = 4_000

SYSTEM_PROMPT = """Você é um recrutador técnico sênior e especialista em triagem de currículos.
Sua tarefa é revisar um currículo (já analisado por regras determinísticas) e produzir
um parecer objetivo, útil e verificável.

Regras obrigatórias:
1. Responda APENAS com um objeto JSON válido, sem markdown, sem comentários.
2. Escreva em português do Brasil.
3. Nunca invente experiências, empresas, formações ou competências que não estejam no texto.
4. Seja específico e acionável; evite frases genéricas.
5. O JSON deve seguir exatamente este formato:
{
  "summary": "resumo em até 600 caracteres",
  "strengths": ["ponto forte 1", "ponto forte 2", "ponto forte 3"],
  "improvements": ["melhoria 1", "melhoria 2", "melhoria 3"],
  "matched_skills": ["competência presente no currículo e relevante"],
  "missing_skills": ["competência exigida pela vaga e ausente no currículo"],
  "confidence": 0.0
}
6. "confidence" é um número entre 0 e 1 indicando sua confiança no parecer.
7. Limite cada lista a no máximo 6 itens."""


def build_user_prompt(context: AnalysisContext) -> str:
    """Serialize the analysis context into a compact, model-friendly prompt."""
    parsed = context.parsed
    result = context.result
    payload = {
        "vaga": {
            "titulo": context.job_title,
            "descricao": (context.job_description or "")[:MAX_JOB_DESCRIPTION_CHARS] or None,
        },
        "curriculo": {
            "texto": context.resume_text[:MAX_RESUME_CHARS],
            "resumo_extraido": parsed.summary[:800],
            "competencias": parsed.skills,
            "anos_experiencia": parsed.metadata.years_experience,
            "formacao": [
                {"curso": entry.degree, "instituicao": entry.institution, "ano": entry.year}
                for entry in parsed.education[:5]
            ],
            "experiencias": [
                {
                    "cargo": entry.title,
                    "empresa": entry.company,
                    "inicio": entry.start_date,
                    "fim": entry.end_date,
                    "atual": entry.is_current,
                    "descricao": entry.description[:500],
                }
                for entry in parsed.experience[:6]
            ],
            "idiomas": [entry.name for entry in parsed.languages],
            "certificacoes": parsed.certifications[:10],
        },
        "analise_deterministica": {
            "score": result.get("overall_score"),
            "veredito": result.get("verdict"),
            "competencias_atendidas": result.get("matched_skills", []),
            "competencias_ausentes": result.get("missing_skills", []),
            "palavras_chave_ausentes": result.get("missing_keywords", []),
        },
    }
    return (
        "Analise o currículo abaixo e gere o parecer no formato JSON solicitado.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
