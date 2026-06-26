SELECT
    p.project_code,
    pr.apartment_count,
    pr.building_count,
    pr.stairwell_count,
    count(DISTINCT ss.id) AS sewer_segment_count,
    count(DISTINCT si.id) AS scope_item_count
FROM core.projects p
LEFT JOIN core.properties pr ON pr.project_id = p.id
LEFT JOIN core.contracts c ON c.project_id = p.id
LEFT JOIN domain.sewer_segments ss ON ss.contract_id = c.id
LEFT JOIN domain.scope_items si ON si.contract_id = c.id
WHERE (%(apartments_count)s::integer IS NULL OR pr.apartment_count IS NOT NULL)
GROUP BY p.project_code, pr.apartment_count, pr.building_count, pr.stairwell_count
ORDER BY
    CASE
        WHEN %(apartments_count)s::integer IS NULL OR pr.apartment_count IS NULL THEN 999999
        ELSE abs(pr.apartment_count - %(apartments_count)s::integer)
    END,
    p.project_code
LIMIT %(limit)s;
