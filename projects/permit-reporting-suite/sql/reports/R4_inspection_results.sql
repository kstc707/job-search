-- R4 Inspection Results by District and Inspection Type.
-- Date filter: Inspection.ScheduledDate. Status filters the parent permit's status.
-- PassRatePct = Pass / (Pass + Fail + Partial); canceled and pending are not completed.
SELECT
    d.DistrictCode,
    it.InspectionTypeCode,
    COUNT(*)                                                    AS Scheduled,
    SUM(CASE WHEN i.Result = 'Pass'     THEN 1 ELSE 0 END)      AS Passed,
    SUM(CASE WHEN i.Result = 'Fail'     THEN 1 ELSE 0 END)      AS Failed,
    SUM(CASE WHEN i.Result = 'Partial'  THEN 1 ELSE 0 END)      AS Partial,
    SUM(CASE WHEN i.Result = 'Canceled' THEN 1 ELSE 0 END)      AS Canceled,
    SUM(CASE WHEN i.Result = 'Pending'  THEN 1 ELSE 0 END)      AS Pending,
    CAST(ROUND(100.0 * SUM(CASE WHEN i.Result = 'Pass' THEN 1 ELSE 0 END)
         / NULLIF(SUM(CASE WHEN i.Result IN ('Pass','Fail','Partial') THEN 1 ELSE 0 END), 0), 1)
         AS decimal(5,1))                                       AS PassRatePct
FROM dbo.Inspection i
JOIN dbo.Permit         p  ON p.PermitId          = i.PermitId
JOIN dbo.District       d  ON d.DistrictId        = p.DistrictId
JOIN dbo.InspectionType it ON it.InspectionTypeId = i.InspectionTypeId
WHERE i.ScheduledDate >= CAST('{?StartDate}' AS date)
  AND i.ScheduledDate <  DATEADD(day, 1, CAST('{?EndDate}' AS date))
  AND ('{?District}' = 'ALL' OR d.DistrictCode = '{?District}')
  AND ('{?Status}'   = 'ALL' OR p.Status       = '{?Status}')
GROUP BY d.DistrictCode, it.InspectionTypeCode
ORDER BY d.DistrictCode, it.InspectionTypeCode;
