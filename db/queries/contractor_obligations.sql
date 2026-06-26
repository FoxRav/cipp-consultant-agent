SELECT obligation_type, obligation_text, trigger_condition, evidence_required
FROM doc.obligations
WHERE contract_id = :contract_id
  AND obligated_role = 'contractor'
ORDER BY obligation_type, obligation_text;

