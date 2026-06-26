SELECT
    p.project_code,
    s.system_type,
    s.flow_order,
    s.segment_type,
    s.segment_name,
    s.included_in_contract,
    s.inclusion_confidence,
    s.boundary_text,
    s.pricing_impact
FROM domain.sewer_segments s
JOIN core.contracts c ON c.id = s.contract_id
JOIN core.projects p ON p.id = c.project_id
ORDER BY p.project_code, s.system_type, s.flow_order;


