def decide(risk_score, evidence, policy_cfg):
    """
    Returns (decision, reasons).

    REVIEW means: block installation until human approval or
    additional evidence. It is not a silent allow.
    """
    status = evidence.get("status")
    package_exists = evidence.get("package_exists")
    version_exists = evidence.get("version_exists")

    review_threshold = float(policy_cfg.get("review_threshold", 0.30))
    block_threshold = float(policy_cfg.get("block_threshold", 0.65))
    block_unresolved = bool(policy_cfg.get("block_unresolved", True))
    review_registry_error = bool(policy_cfg.get("review_on_registry_error", True))

    # 1. Package does not exist
    if status == "package_not_found" or package_exists is False:
        return ("BLOCK", ["package_not_found"])

    # 2. Registry error
    if status == "registry_error" or package_exists is None:
        if review_registry_error:
            return ("REVIEW", ["registry_error"])
        return ("BLOCK", ["registry_error_unresolved"])

    # 3. Version requested but not found
    if status == "version_not_found" or version_exists is False:
        if block_unresolved:
            return ("REVIEW", ["version_not_found"])
        return ("REVIEW", ["version_not_found_nonblocking"])

    # 4. Verified package + version
    if status == "verified" and package_exists is True:
        # Unversioned installs are a supply-chain risk: latest can change.
        if version_exists is None and not evidence.get("requested_version"):
            return ("REVIEW", ["unpinned_requires_review"])
        if risk_score >= block_threshold:
            return ("BLOCK", ["risk_score_above_block_threshold"])
        if risk_score >= review_threshold:
            return ("REVIEW", ["risk_score_above_review_threshold"])
        return ("ALLOW", ["no_blocking_findings"])

    # 5. Unknown
    return ("REVIEW", ["insufficient_registry_evidence"])