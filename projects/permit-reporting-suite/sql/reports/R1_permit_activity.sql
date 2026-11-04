-- R1 Permit Activity Summary
-- Crystal: Database Expert > Add Command. Parameters (String): StartDate, EndDate (YYYY-MM-DD),
-- District (code or ALL), Status (permit status or ALL). Date filter: Permit.AppliedDate.
SELECT
    d.DistrictCode,
    pt.PermitTypeCode,
    p.Status,
    COUNT(*)                                               AS PermitCount,
    COALESCE(SUM(p.Valuation), 0)                          AS TotalValuation,
    SUM(CASE WHEN p.Valuation IS NULL THEN 1 ELSE 0 END)   AS MissingValuationCount
FROM dbo.Permit p
JOIN dbo.District   d  ON d.DistrictId   = p.DistrictId
JOIN dbo.PermitType pt ON pt.PermitTypeId = p.PermitTypeId
WHERE p.AppliedDate >= CAST('{?StartDate}' AS date)
  AND p.AppliedDate <  DATEADD(day, 1, CAST('{?EndDate}' AS date))
  AND ('{?District}' = 'ALL' OR d.DistrictCode = '{?District}')
  AND ('{?Status}'   = 'ALL' OR p.Status       = '{?Status}')
GROUP BY d.DistrictCode, pt.PermitTypeCode, p.Status
ORDER BY d.DistrictCode, pt.PermitTypeCode, p.Status;
