SELECT
    p.project_code,
    s.entity_type AS subject_type,
    s.canonical_name AS subject_name,
    r.relation_type,
    o.entity_type AS object_type,
    o.canonical_name AS object_name,
    r.confidence,
    r.extraction_method,
    r.id AS relation_id
FROM kg.relations r
JOIN kg.entities s ON s.id = r.subject_entity_id
JOIN kg.entities o ON o.id = r.object_entity_id
LEFT JOIN core.projects p ON p.id = r.project_id
WHERE p.project_code = %(project_code)s
ORDER BY s.entity_type, s.canonical_name, r.relation_type, o.entity_type, o.canonical_name;
