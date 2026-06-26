SELECT
    e.id,
    e.entity_type,
    e.canonical_name,
    e.source_table,
    e.source_id,
    p.project_code
FROM kg.entities e
LEFT JOIN core.projects p ON p.id = e.project_id
WHERE e.entity_type = ANY(%(entity_types)s)
   OR e.canonical_name ILIKE ANY(%(keyword_patterns)s)
ORDER BY e.entity_type, e.canonical_name
LIMIT %(limit)s;
