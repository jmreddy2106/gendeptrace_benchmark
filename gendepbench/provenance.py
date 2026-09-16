from .utils import now_iso, sha256_json


def make_adar(task, generation, dependency, evidence, osv, risk, decision):
    record = {
        "adar_version": "0.1",
        "task_id": task["task_id"],
        "scenario": task["scenario"],
        "ecosystem": task["ecosystem"],
        "model_id": generation.get("model_id"),
        "model_revision": generation.get("model_revision"),
        "prompt_sha256": generation.get("prompt_sha256"),
        "output_sha256": generation.get("output_sha256"),
        "generation_timestamp": generation.get("timestamp"),
        "dependency": dependency,
        "registry_evidence_hash": evidence.get("evidence_hash"),
        "registry_retrieved_at": evidence.get("retrieved_at"),
        "osv_evidence_hash": osv.get("_evidence_hash") if osv else None,
        "risk_score": risk,
        "decision": decision,
        "created_at": now_iso(),
    }
    record["adar_sha256"] = sha256_json(record)
    return record


def make_gdpg(task, generation, dependency_records):
    nodes = [
        {"id": "p:" + (generation.get("prompt_sha256") or ""),
         "type": "prompt"},
        {"id": "m:" + (generation.get("model_id") or "unknown"),
         "type": "model"},
        {"id": "o:" + (generation.get("output_sha256") or ""),
         "type": "output"},
        {"id": "b:" + task["task_id"], "type": "build_artifact"},
    ]
    edges = [
        ["p:" + (generation.get("prompt_sha256") or ""),
         "m:" + (generation.get("model_id") or "unknown")],
        ["m:" + (generation.get("model_id") or "unknown"),
         "o:" + (generation.get("output_sha256") or "")],
    ]
    for i, r in enumerate(dependency_records):
        did = f"d:{i}:{r['dependency']['name']}"
        nodes.append({"id": did, "type": "dependency",
                      "name": r["dependency"]["name"]})
        edges.append(["o:" + (generation.get("output_sha256") or ""), did])
        edges.append([did, "b:" + task["task_id"]])
    return {"graph_version": "0.1",
            "task_id": task["task_id"],
            "nodes": nodes, "edges": edges}