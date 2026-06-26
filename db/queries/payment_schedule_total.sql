SELECT
    SUM(amount_net) AS total_net,
    SUM(vat_amount) AS total_vat,
    SUM(amount_gross) AS total_gross
FROM finance.payment_schedule_items
WHERE contract_id = :contract_id;

