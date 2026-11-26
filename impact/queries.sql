-- Reporting queries over impact/results/impact.db (sqlite3 impact/results/impact.db < impact/queries.sql)
.headers on
.mode column

-- 1. Technique comparison: precision cost vs safety
SELECT technique,
       ROUND(mean_fraction_selected, 3) AS fraction_selected,
       detected || '/' || faulty_changes AS faulty_detected,
       fully_safe || '/' || faulty_changes AS fully_safe,
       ROUND(failing_test_recall, 3) AS failing_test_recall
FROM technique_summary ORDER BY fully_safe DESC, mean_fraction_selected;

-- 2. Every failing test a technique did NOT select (missed regressions), with the change that caused it
SELECT s.technique, c.id AS change_id, c.entity, o.test AS missed_test, c.after
FROM outcomes o
JOIN changes c ON c.id = o.change_id
CROSS JOIN (SELECT DISTINCT technique FROM selections) s
WHERE o.failed = 1
  AND NOT EXISTS (SELECT 1 FROM selections x WHERE x.technique = s.technique AND x.change_id = o.change_id AND x.test = o.test)
  AND s.technique IN ('declared_manifest', 'static_call_graph', 'dynamic_coverage', 'hybrid')
ORDER BY s.technique, c.id LIMIT 40;

-- 3. Downstream reach: tests in OTHER components that fail when a shared helper changes
SELECT c.entity, t.declared_file AS failing_test_component, COUNT(DISTINCT o.test) AS failing_tests
FROM outcomes o JOIN changes c ON c.id = o.change_id JOIN tests t ON t.name = o.test
WHERE o.failed = 1 AND c.entity IN ('age_ms', 'clamp_int', 'validate_sample', 'rate_limit')
GROUP BY c.entity, t.declared_file ORDER BY c.entity, failing_tests DESC;

-- 4. Changes the whole suite misses (candidates for new tests)
SELECT c.id, c.file, c.operator, c.before, c.after
FROM changes c WHERE c.compiled = 1
  AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.change_id = c.id AND o.failed = 1);

-- 5. Assistant evaluation: pass rate per assistant and category
SELECT assistant, category, SUM(passed) || '/' || COUNT(*) AS passed
FROM assistant_eval GROUP BY assistant, category ORDER BY assistant, category;

-- 6. Edges a direct-call graph cannot see
SELECT caller, callee FROM call_edges WHERE kind = 'function_pointer';
