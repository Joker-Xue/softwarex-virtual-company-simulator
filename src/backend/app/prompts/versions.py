from app.prompts.agent_prompt import TASK_GENERATION_PROMPT

PROMPT_VERSIONS = {
    "agent_task": {
        "v1.0": {
            "template": TASK_GENERATION_PROMPT,
            "created_at": "2026-04-09",
            "notes": "SoftwareX public simulator artifact baseline",
        },
    },
}

ACTIVE_VERSIONS = {
    "agent_task": "v1.0",
}


def get_prompt(module: str, version: str | None = None) -> dict:
    if module not in PROMPT_VERSIONS:
        raise KeyError(f"Unknown prompt Module: {module}")
    version = version or ACTIVE_VERSIONS.get(module)
    if not version or version not in PROMPT_VERSIONS[module]:
        raise KeyError(f"Module {module} does not exist version {version}")
    return PROMPT_VERSIONS[module][version]


def list_versions(module: str) -> list[str]:
    if module not in PROMPT_VERSIONS:
        return []
    return sorted(PROMPT_VERSIONS[module].keys())


def get_active_version(module: str) -> str | None:
    return ACTIVE_VERSIONS.get(module)
