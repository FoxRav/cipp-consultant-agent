SELECT document_type, attachment_no, document_title_redacted, precedence_rank, document_date
FROM core.contract_documents
WHERE contract_id = :contract_id
ORDER BY precedence_rank NULLS LAST, document_type;

