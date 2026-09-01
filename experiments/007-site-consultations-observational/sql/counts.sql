-- Experiment 007 pre-freeze count checks (READ-ONLY; count-only checks are
-- allowed before the freeze — joint distributions are not).
-- Run interactively; paste outputs into results/audit.txt notes.

-- C1: executions and searches by platform (capture-path sanity: expect
--     openai + gemini + a small claude tail; perplexity/AIO ~0 by design)
SELECT COALESCE(NULLIF(TRIM(gse.platform), ''), 'unknown') AS platform,
       COUNT(*)                              AS executions,
       COUNT(DISTINCT gse."groundingSearchId") AS distinct_searches,
       COUNT(*) FILTER (WHERE gs."siteScopeDomain" IS NOT NULL) AS scoped
FROM grounding_search_executions gse
JOIN grounding_searches gs ON gs.id = gse."groundingSearchId"
GROUP BY 1 ORDER BY executions DESC;

-- C2: weekly_grounding share (Audit E denominator)
SELECT pr."runType", COUNT(*) AS executions
FROM grounding_search_executions gse
LEFT JOIN "DiscoveryQueryExecution" dqe ON dqe.id = gse."discoveryExecutionId"
LEFT JOIN prompt_runs pr ON pr.id = dqe."promptRunId"
GROUP BY 1 ORDER BY executions DESC;

-- C3: null-rate of the prompt link (rows where neither prompt path resolves)
SELECT COUNT(*)                                    AS executions,
       COUNT(*) FILTER (WHERE dqe.id IS NULL)      AS no_discovery_execution,
       COUNT(*) FILTER (WHERE dqe.id IS NOT NULL
                        AND pr."propertyQueryId" IS NULL
                        AND rde."propertyQueryId" IS NULL) AS no_property_query
FROM grounding_search_executions gse
LEFT JOIN "DiscoveryQueryExecution" dqe ON dqe.id = gse."discoveryExecutionId"
LEFT JOIN prompt_runs pr ON pr.id = dqe."promptRunId"
LEFT JOIN "ReportDiscoveryExecution" rde ON rde.id = dqe."reportExecutionId";

-- C4: metric coverage for scoped domains (Audit D numerators)
SELECT COUNT(DISTINCT gs."siteScopeDomain")                    AS scoped_domains,
       COUNT(DISTINCT ccr.domain)                              AS with_hc_rank,
       COUNT(DISTINCT pub.domain)                              AS with_publisher
FROM grounding_searches gs
LEFT JOIN common_crawl_domain_ranks ccr ON ccr.domain = gs."siteScopeDomain"
LEFT JOIN "Publisher" pub               ON pub.domain = gs."siteScopeDomain"
WHERE gs."siteScopeDomain" IS NOT NULL;

-- C5: total-graph-nodes denominator for percentile derivation
SELECT key, value FROM common_crawl_metadata WHERE key = 'total_graph_nodes';
