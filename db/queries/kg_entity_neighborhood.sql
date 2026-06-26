SELECT
    e.id AS center_entity_id,
    e.entity_type AS center_type,
    e.canonical_name AS center_name,
    'outgoing' AS direction,
    r.relation_type,
    n.id AS neighbor_entity_id,
    n.entity_type AS neighbor_type,
    n.canonical_name AS neighbor_name,
    r.id AS relation_id,
    r.confidence
FROM kg.entities e
JOIN kg.relations r ON r.subject_entity_id = e.id
JOIN kg.entities n ON n.id = r.object_entity_id
WHERE e.id = %(entity_id)s
UNION ALL
SELECT
    e.id AS center_entity_id,
    e.entity_type AS center_type,
    e.canonical_name AS center_name,
    'incoming' AS direction,
    r.relation_type,
    n.id AS neighbor_entity_id,
    n.entity_type AS neighbor_type,
    n.canonical_name AS neighbor_name,
    r.id AS relation_id,
    r.confidence
FROM kg.entities e
JOIN kg.relations r ON r.object_entity_id = e.id
JOIN kg.entities n ON n.id = r.subject_entity_id
WHERE e.id = %(entity_id)s
ORDER BY direction, relation_type, neighbor_type, neighbor_name;
