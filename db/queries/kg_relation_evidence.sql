SELECT
    r.id AS relation_id,
    s.entity_type AS subject_type,
    s.canonical_name AS subject_name,
    r.relation_type,
    o.entity_type AS object_type,
    o.canonical_name AS object_name,
    ev.source_table,
    ev.source_id,
    ev.source_file_id,
    ev.page_id,
    ev.section_id,
    ev.clause_id,
    ev.extraction_run_id,
    ev.evidence_note,
    ev.confidence
FROM kg.relations r
JOIN kg.entities s ON s.id = r.subject_entity_id
JOIN kg.entities o ON o.id = r.object_entity_id
LEFT JOIN kg.evidence ev ON ev.relation_id = r.id
WHERE r.id = %(relation_id)s
ORDER BY ev.created_at;
