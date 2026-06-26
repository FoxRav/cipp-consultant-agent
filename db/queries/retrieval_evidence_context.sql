SELECT
    ev.id AS evidence_id,
    ev.entity_id,
    ev.relation_id,
    ev.source_table,
    ev.source_id,
    ev.source_file_id,
    ev.section_id,
    ev.clause_id,
    ev.page_id,
    ev.evidence_note,
    ev.confidence
FROM kg.evidence ev
WHERE ev.entity_id = ANY(%(entity_ids)s)
   OR ev.relation_id = ANY(%(relation_ids)s)
ORDER BY ev.confidence DESC, ev.created_at
LIMIT %(limit)s;
