-- R6 Inspector Workload.
-- Date filter: Inspection.ScheduledDate. District and Status filter the parent permit.
-- DistinctPermits is not additive across inspectors, so the report does not total it.
SELECT
    ins.InspectorName,
    hd.DistrictCode                                                       AS HomeDistrict,
    COUNT(*)                                                              AS Assigned,
    SUM(CASE WHEN i.Result IN ('Pass','Fail','Partial') THEN 1 ELSE 0 END) AS Completed,
    SUM(CASE WHEN i.Result = 'Pass'     THEN 1 ELSE 0 END)                AS Passed,
    SUM(CASE WHEN i.Result = 'Fail'     THEN 1 ELSE 0 END)                AS Failed,
    SUM(CASE WHEN i.Result = 'Canceled' THEN 1 ELSE 0 END)                AS Canceled,
    COUNT(DISTINCT i.PermitId)                                            AS DistinctPermits
FROM dbo.Inspection i
JOIN dbo.Permit    p   ON p.PermitId    = i.PermitId
JOIN dbo.District  d   ON d.DistrictId  = p.DistrictId
JOIN dbo.Inspector ins ON ins.InspectorId = i.InspectorId
JOIN dbo.District  hd  ON hd.DistrictId = ins.HomeDistrictId
WHERE i.ScheduledDate >= CAST('{?StartDate}' AS date)
  AND i.ScheduledDate <  DATEADD(day, 1, CAST('{?EndDate}' AS date))
  AND ('{?District}' = 'ALL' OR d.DistrictCode = '{?District}')
  AND ('{?Status}'   = 'ALL' OR p.Status       = '{?Status}')
GROUP BY ins.InspectorName, hd.DistrictCode
ORDER BY ins.InspectorName;
