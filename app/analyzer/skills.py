"""Canonical skill catalog and alias-aware matching.

The catalog is deliberately data-driven: adding a skill is a one-line change.
Matching is accent-insensitive, case-insensitive and tolerant to common
separators (``node.js`` / ``nodejs`` / ``node js``), while word boundaries stop
``java`` from matching ``javascript``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.analyzer.text import normalize


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    category: str
    aliases: tuple[str, ...] = ()


def _skill(name: str, category: str, *aliases: str) -> Skill:
    return Skill(name=name, category=category, aliases=aliases)


PROGRAMMING = "Programming"
FRONTEND = "Frontend"
BACKEND = "Backend"
DATA_AI = "Data & AI"
CLOUD_DEVOPS = "Cloud & DevOps"
TESTING = "Testing & Quality"
PRACTICES = "Engineering Practices"
SOFT = "Soft Skills"

SKILL_CATALOG: tuple[Skill, ...] = (
    # -- Programming --------------------------------------------------------
    _skill("Python", PROGRAMMING, "python", "py"),
    _skill("Java", PROGRAMMING, "java"),
    _skill("JavaScript", PROGRAMMING, "javascript", "js", "ecmascript"),
    _skill("TypeScript", PROGRAMMING, "typescript", "ts"),
    _skill("C#", PROGRAMMING, "c#", "csharp", "c sharp", ".net", "dotnet"),
    _skill("C++", PROGRAMMING, "c++", "cpp"),
    _skill("C", PROGRAMMING, "linguagem c", "programacao em c"),
    _skill("Go", PROGRAMMING, "golang", "go"),
    _skill("Rust", PROGRAMMING, "rust"),
    _skill("Ruby", PROGRAMMING, "ruby"),
    _skill("PHP", PROGRAMMING, "php"),
    _skill("Swift", PROGRAMMING, "swift"),
    _skill("Kotlin", PROGRAMMING, "kotlin"),
    _skill("Scala", PROGRAMMING, "scala"),
    _skill("R", PROGRAMMING, "linguagem r", "r language"),
    _skill("MATLAB", PROGRAMMING, "matlab"),
    _skill("Bash/Shell", PROGRAMMING, "bash", "shell script", "shell scripting", "shell"),
    _skill("PowerShell", PROGRAMMING, "powershell"),
    _skill("VBA", PROGRAMMING, "vba", "visual basic"),
    # -- Frontend -----------------------------------------------------------
    _skill("React", FRONTEND, "react", "react.js", "reactjs"),
    _skill("Angular", FRONTEND, "angular", "angularjs"),
    _skill("Vue.js", FRONTEND, "vue", "vue.js", "vuejs"),
    _skill("Next.js", FRONTEND, "next.js", "nextjs", "next js"),
    _skill("HTML", FRONTEND, "html", "html5"),
    _skill("CSS", FRONTEND, "css", "css3"),
    _skill("Sass", FRONTEND, "sass", "scss"),
    _skill("Tailwind CSS", FRONTEND, "tailwind", "tailwind css", "tailwindcss"),
    _skill("Redux", FRONTEND, "redux"),
    _skill("Webpack", FRONTEND, "webpack"),
    _skill("Accessibility", FRONTEND, "acessibilidade", "accessibility", "wcag"),
    # -- Backend ------------------------------------------------------------
    _skill("Node.js", BACKEND, "node.js", "nodejs", "node js"),
    _skill("Django", BACKEND, "django"),
    _skill("Flask", BACKEND, "flask"),
    _skill("FastAPI", BACKEND, "fastapi", "fast api"),
    _skill("Spring Boot", BACKEND, "spring boot", "spring"),
    _skill("Laravel", BACKEND, "laravel"),
    _skill("Ruby on Rails", BACKEND, "ruby on rails", "rails"),
    _skill("Express.js", BACKEND, "express", "express.js", "expressjs"),
    _skill("GraphQL", BACKEND, "graphql"),
    _skill("REST APIs", BACKEND, "rest", "rest api", "restful", "api rest", "apis rest"),
    _skill("gRPC", BACKEND, "grpc"),
    _skill("Microservices", BACKEND, "microservices", "microsservicos", "micro servicos"),
    _skill("WebSockets", BACKEND, "websocket", "websockets"),
    # -- Data & AI ----------------------------------------------------------
    _skill("SQL", DATA_AI, "sql"),
    _skill("MySQL", DATA_AI, "mysql"),
    _skill("PostgreSQL", DATA_AI, "postgresql", "postgres"),
    _skill("Oracle Database", DATA_AI, "oracle", "oracle database"),
    _skill("SQL Server", DATA_AI, "sql server", "mssql"),
    _skill("MongoDB", DATA_AI, "mongodb", "mongo"),
    _skill("Redis", DATA_AI, "redis"),
    _skill("Elasticsearch", DATA_AI, "elasticsearch", "elastic search"),
    _skill("Kafka", DATA_AI, "kafka", "apache kafka"),
    _skill("Apache Spark", DATA_AI, "spark", "apache spark", "pyspark"),
    _skill("Hadoop", DATA_AI, "hadoop"),
    _skill("Airflow", DATA_AI, "airflow", "apache airflow"),
    _skill("dbt", DATA_AI, "dbt"),
    _skill("Snowflake", DATA_AI, "snowflake"),
    _skill("BigQuery", DATA_AI, "bigquery", "big query"),
    _skill("Pandas", DATA_AI, "pandas"),
    _skill("NumPy", DATA_AI, "numpy"),
    _skill("scikit-learn", DATA_AI, "scikit-learn", "sklearn", "scikit learn"),
    _skill("TensorFlow", DATA_AI, "tensorflow"),
    _skill("PyTorch", DATA_AI, "pytorch", "torch"),
    _skill("Machine Learning", DATA_AI, "machine learning", "aprendizado de maquina", "ml"),
    _skill("Deep Learning", DATA_AI, "deep learning", "redes neurais", "neural networks"),
    _skill(
        "NLP",
        DATA_AI,
        "nlp",
        "natural language processing",
        "processamento de linguagem natural",
    ),
    _skill("Computer Vision", DATA_AI, "computer vision", "visao computacional"),
    _skill("LLMs", DATA_AI, "llm", "llms", "large language models", "modelos de linguagem"),
    _skill("Power BI", DATA_AI, "power bi", "powerbi"),
    _skill("Tableau", DATA_AI, "tableau"),
    _skill("Excel", DATA_AI, "excel", "microsoft excel"),
    _skill("ETL", DATA_AI, "etl", "pipeline de dados", "data pipeline", "data pipelines"),
    _skill("Data Modeling", DATA_AI, "data modeling", "modelagem de dados"),
    _skill("Databricks", DATA_AI, "databricks"),
    # -- Cloud & DevOps -----------------------------------------------------
    _skill("AWS", CLOUD_DEVOPS, "aws", "amazon web services"),
    _skill("Azure", CLOUD_DEVOPS, "azure", "microsoft azure"),
    _skill("GCP", CLOUD_DEVOPS, "gcp", "google cloud", "google cloud platform"),
    _skill("Docker", CLOUD_DEVOPS, "docker", "containers"),
    _skill("Kubernetes", CLOUD_DEVOPS, "kubernetes", "k8s"),
    _skill("Terraform", CLOUD_DEVOPS, "terraform"),
    _skill("Ansible", CLOUD_DEVOPS, "ansible"),
    _skill("Jenkins", CLOUD_DEVOPS, "jenkins"),
    _skill("GitHub Actions", CLOUD_DEVOPS, "github actions", "github action"),
    _skill("GitLab CI", CLOUD_DEVOPS, "gitlab ci", "gitlab-ci"),
    _skill(
        "CI/CD",
        CLOUD_DEVOPS,
        "ci/cd",
        "cicd",
        "continuous integration",
        "integracao continua",
        "entrega continua",
    ),
    _skill("Linux", CLOUD_DEVOPS, "linux", "ubuntu", "debian"),
    _skill("Nginx", CLOUD_DEVOPS, "nginx"),
    _skill("AWS Lambda", CLOUD_DEVOPS, "aws lambda", "lambda functions", "funcoes lambda"),
    _skill(
        "Observability", CLOUD_DEVOPS, "observabilidade", "observability", "prometheus", "grafana"
    ),
    _skill("Serverless", CLOUD_DEVOPS, "serverless"),
    # -- Testing & Quality --------------------------------------------------
    _skill("Unit Testing", TESTING, "testes unitarios", "unit testing", "pytest", "junit", "jest"),
    _skill("TDD", TESTING, "tdd", "test-driven development", "test driven development"),
    _skill("Integration Testing", TESTING, "testes de integracao", "integration testing"),
    _skill("Selenium", TESTING, "selenium"),
    _skill("Cypress", TESTING, "cypress"),
    _skill("Playwright", TESTING, "playwright"),
    _skill("Load Testing", TESTING, "testes de carga", "load testing", "k6", "jmeter"),
    # -- Engineering practices ---------------------------------------------
    _skill("Git", PRACTICES, "git", "versionamento", "version control", "gitflow"),
    _skill("Scrum", PRACTICES, "scrum"),
    _skill("Kanban", PRACTICES, "kanban"),
    _skill(
        "Agile",
        PRACTICES,
        "agile",
        "agil",
        "metodologias ageis",
        "agile methodologies",
        "sprint",
    ),
    _skill("Design Patterns", PRACTICES, "design patterns", "padroes de projeto", "design pattern"),
    _skill("SOLID", PRACTICES, "solid"),
    _skill("Clean Code", PRACTICES, "clean code", "codigo limpo"),
    _skill("Code Review", PRACTICES, "code review", "revisao de codigo"),
    _skill("Jira", PRACTICES, "jira"),
    _skill("Documentation", PRACTICES, "documentacao", "documentation", "technical writing"),
    # -- Soft skills --------------------------------------------------------
    _skill("Communication", SOFT, "comunicacao", "communication", "comunicativo", "comunicativa"),
    _skill("Leadership", SOFT, "lideranca", "leadership", "lider", "lider de equipe"),
    _skill("Teamwork", SOFT, "trabalho em equipe", "teamwork", "colaboracao", "collaboration"),
    _skill(
        "Problem Solving",
        SOFT,
        "resolucao de problemas",
        "problem solving",
        "pensamento critico",
        "critical thinking",
    ),
    _skill("Adaptability", SOFT, "adaptabilidade", "adaptability", "flexibilidade", "flexibility"),
    _skill("Time Management", SOFT, "gestao de tempo", "time management", "organizacao"),
    _skill("Proactivity", SOFT, "proatividade", "proactive", "proatividade"),
    _skill("Mentoring", SOFT, "mentoria", "mentoring", "mentor"),
    _skill("Stakeholder Management", SOFT, "stakeholders", "gestao de stakeholders"),
)

SKILLS_BY_NAME: dict[str, Skill] = {skill.name: skill for skill in SKILL_CATALOG}

CATEGORY_ORDER: tuple[str, ...] = (
    PROGRAMMING,
    FRONTEND,
    BACKEND,
    DATA_AI,
    CLOUD_DEVOPS,
    TESTING,
    PRACTICES,
    SOFT,
)

ALL_SKILL_NAMES: tuple[str, ...] = tuple(skill.name for skill in SKILL_CATALOG)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    tokens = normalize(alias).split()
    body = r"[\s\-_/]*".join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<![a-z0-9+#]){body}(?![a-z0-9+#])")


@lru_cache(maxsize=1)
def _compiled_catalog() -> tuple[tuple[str, re.Pattern[str]], ...]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    seen_aliases: set[str] = set()
    for skill in SKILL_CATALOG:
        aliases = skill.aliases or (skill.name,)
        for alias in aliases:
            key = normalize(alias)
            if not key or key in seen_aliases:
                continue
            seen_aliases.add(key)
            compiled.append((skill.name, _alias_pattern(alias)))
    return tuple(compiled)


def find_skills(text: str) -> list[str]:
    """Return canonical skill names mentioned in *text*, alphabetically sorted."""
    if not text:
        return []
    haystack = normalize(text)
    if not haystack:
        return []
    found = {name for name, pattern in _compiled_catalog() if pattern.search(haystack)}
    return sorted(found)


def categorize(skill_name: str) -> str:
    """Return the category of a canonical skill (or ``"Other"``)."""
    skill = SKILLS_BY_NAME.get(skill_name)
    return skill.category if skill else "Other"


def group_skills(skill_names: list[str]) -> dict[str, list[str]]:
    """Group canonical skills by category, preserving the catalog category order."""
    grouped: dict[str, list[str]] = {}
    for name in skill_names:
        grouped.setdefault(categorize(name), []).append(name)
    ordered: dict[str, list[str]] = {}
    for category in CATEGORY_ORDER:
        if category in grouped:
            ordered[category] = sorted(grouped[category])
    for category, names in grouped.items():
        if category not in ordered:
            ordered[category] = sorted(names)
    return ordered


def technical_skills(skill_names: list[str]) -> list[str]:
    """Filter out soft skills, keeping hard/technical skills."""
    return [name for name in skill_names if categorize(name) != SOFT]
