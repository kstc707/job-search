-- R2 Fee Revenue by District and Fee Type (voided fees excluded).
-- Date filter: Fee.AssessedDate. Collected counts only payments dated on or before EndDate.
-- Status filters the parent permit's status.
SELECT
    d.DistrictCode,
    ft.FeeTypeCode,
    COUNT(*)                                                         AS FeeCount,
    SUM(f.Amount)                                                    AS Assessed,
    SUM(CASE WHEN f.PaidDate < DATEADD(day, 1, CAST('{?EndDate}' AS date))
             THEN f.PaidAmount ELSE 0 END)                           AS Collected,
    SUM(f.Amount) - SUM(CASE WHEN f.PaidDate < DATEADD(day, 1, CAST('{?EndDate}' AS date))
             THEN f.PaidAmount ELSE 0 END)                           AS Outstanding
FROM dbo.Fee f
JOIN dbo.Permit   p  ON p.PermitId   = f.PermitId
JOIN dbo.District d  ON d.DistrictId = p.DistrictId
JOIN dbo.FeeType  ft ON ft.FeeTypeId = f.FeeTypeId
WHERE f.IsVoided = 0
  AND f.AssessedDate >= CAST('{?StartDate}' AS date)
  AND f.AssessedDate <  DATEADD(day, 1, CAST('{?EndDate}' AS date))
  AND ('{?District}' = 'ALL' OR d.DistrictCode = '{?District}')
  AND ('{?Status}'   = 'ALL' OR p.Status       = '{?Status}')
GROUP BY d.DistrictCode, ft.FeeTypeCode
ORDER BY d.DistrictCode, ft.FeeTypeCode;
