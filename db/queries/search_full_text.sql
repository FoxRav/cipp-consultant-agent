SELECT c.id,
       c.chunk_type,
       c.content_redacted,
       ts_rank(c.search_vector_fi, plainto_tsquery('finnish', :query)) AS rank_fi,
       ts_rank(c.search_vector_simple, plainto_tsquery('simple', :query)) AS rank_simple
FROM rag.chunks c
WHERE c.search_vector_fi @@ plainto_tsquery('finnish', :query)
   OR c.search_vector_simple @@ plainto_tsquery('simple', :query)
ORDER BY GREATEST(
    ts_rank(c.search_vector_fi, plainto_tsquery('finnish', :query)),
    ts_rank(c.search_vector_simple, plainto_tsquery('simple', :query))
) DESC
LIMIT 20;
