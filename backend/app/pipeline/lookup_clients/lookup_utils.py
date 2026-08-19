def resolve_rule_value_sets(
    literals: dict[str, list[str]],
    rule: dict,
    include_optional: bool = True,
) -> list[dict[str, str]]:
    """
    Reolves a rule from `search_queries`in the config into a list of value dicts mapping predicates to literal value used for querying.
    If `include_optional` is True, optional predicates will be included in the value sets if they have values.
    """
    predicates = rule.get("predicates", [])
    optional_predicates = (
        rule.get("optional_predicates", []) if include_optional else []
    )

    if not predicates:
        return []

    require_all = rule.get("require_all", False)
    # get the values for each predicate of the rule
    value_lists = [
        [
            value.strip()
            for value in literals.get(predicate, [])
            if value and value.strip()
        ]
        for predicate in predicates
    ]

    if require_all and any(not values for values in value_lists):
        return []

    def with_optional(value_set: dict[str, str]) -> dict[str, str]:
        # Add optional predicates to the value set if they have values.
        for predicate in optional_predicates:
            values = [
                value.strip()
                for value in literals.get(predicate, [])
                if value and value.strip()
            ]
            if values:
                value_set[predicate] = values[0]
        return value_set

    # One predicate: each literal value becomes its own query
    if len(predicates) == 1:
        return [with_optional({predicates[0]: value}) for value in value_lists[0]]

    # Multiple predicates: combine the first value of each predicate
    value_set = {
        predicate: values[0]
        for predicate, values in zip(predicates, value_lists, strict=True)
        if values
    }

    if not value_set:
        return []
    return [with_optional(value_set)]


def has_sufficient_data(literals: dict[str, list[str]], type_config: dict) -> bool:
    """
    Check an entity-type config's `require_any_of`.
    Returns true if at least one of the required literals is present, or if no
    `require_any_of` is configured at all.
    """
    require_any_of = type_config.get("require_any_of")
    if not require_any_of:
        return True
    return any(literals.get(key) for key in require_any_of)
