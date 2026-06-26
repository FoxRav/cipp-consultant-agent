SELECT
    r.id AS relation_id,
    s.entity_type AS subject_type,
    s.canonical_name AS subject_name,
    r.relation_type,
    o.entity_type AS object_type,
    o.canonical_name AS object_name,
    p.project_code
FROM kg.relations r
JOIN kg.entities s ON s.id = r.subject_entity_id
JOIN kg.entities o ON o.id = r.object_entity_id
LEFT JOIN core.projects p ON p.id = r.project_id
WHERE r.subject_entity_id = ANY(%(entity_ids)s)
   OR r.object_entity_id = ANY(%(entity_ids)s)
ORDER BY r.relation_type, subject_type, object_type
LIMIT %(limit)s;
