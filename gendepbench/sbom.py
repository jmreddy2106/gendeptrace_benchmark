from .utils import now_iso, sha256_json


def make_cyclonedx(task, generation, dependency_records):
    components = []
    for r in dependency_records:
        dep = r["dependency"]
        evidence = r["evidence"]
        name = dep["name"]
        version = (evidence.get("resolved_version")
                   or dep.get("requested_version") or "UNKNOWN")
        purl = f"pkg:{'pypi' if task['ecosystem'] == 'PyPI' else 'npm'}/{name}@{version}"
        components.append({
            "type": "library",
            "bom-ref": purl,
            "name": name,
            "version": version,
            "purl": purl,
            "properties": [
                {"name": "gendepbench:risk_score",
                 "value": str(r["risk_score"])},
                {"name": "gendepbench:decision",
                 "value": r["decision"]},
                {"name": "gendepbench:source",
                 "value": dep.get("source", "unknown")},
            ],
        })
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": now_iso(),
            "component": {
                "type": "application",
                "name": f"gendepbench-{task['task_id']}",
                "version": "1.0.0",
            },
            "properties": [
                {"name": "genai:model",
                 "value": generation.get("model_id", "unknown")},
                {"name": "genai:prompt_sha256",
                 "value": generation.get("prompt_sha256", "")},
                {"name": "genai:output_sha256",
                 "value": generation.get("output_sha256", "")},
            ],
        },
        "components": components,
    }
    bom["metadata"]["properties"].append({
        "name": "gendepbench:bom_sha256",
        "value": sha256_json(bom),
    })
    return bom