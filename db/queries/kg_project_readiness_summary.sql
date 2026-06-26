SELECT
    p.project_code,
    count(DISTINCT e.id) AS entity_count,
    count(DISTINCT r.id) AS relation_count,
    count(DISTINCT ev.id) AS evidence_count,
    count(DISTINCT e.id) FILTER (WHERE ev_entity.id IS NULL) AS entities_without_evidence,
    count(DISTINCT r.id) FILTER (WHERE ev_relation.id IS NULL) AS relations_without_evidence
FROM core.projects p
LEFT JOIN kg.entities e ON e.project_id = p.id
LEFT JOIN kg.relations r ON r.project_id = p.id
LEFT JOIN kg.evidence ev ON ev.entity_id = e.id OR ev.relation_id = r.id
LEFT JOIN kg.evidence ev_entity ON ev_entity.entity_id = e.id
LEFT JOIN kg.evidence ev_relation ON ev_relation.relation_id = r.id
GROUP BY p.project_code
ORDER BY p.project_code;
