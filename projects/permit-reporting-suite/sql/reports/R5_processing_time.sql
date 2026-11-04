-- R5 Permit Processing Time (applied -> issued) by Permit Type.
-- Issued permits whose AppliedDate is in the range. Median and P90 use PERCENTILE_CONT
-- (linear interpolation), which is a window function, so it is computed in its own CTE.
WITH x AS (
    SELECT
        pt.PermitTypeCode,
        pt.TargetDays,
        DATEDIFF(day, p.AppliedDate, p.IssuedDate) AS Days
    FROM dbo.Permit p
    JOIN dbo.District   d  ON d.DistrictId    = p.DistrictId
    JOIN dbo.PermitType pt ON pt.PermitTypeId = p.PermitTypeId
    WHERE p.IssuedDate IS NOT NULL
      AND p.AppliedDate >= CAST('{?StartDate}' AS date)
      AND p.AppliedDate <  DATEADD(day, 1, CAST('{?EndDate}' AS date))
      AND ('{?District}' = 'ALL' OR d.DistrictCode = '{?District}')
      AND ('{?Status}'   = 'ALL' OR p.Status       = '{?Status}')
),
pct AS (
    SELECT DISTINCT
        PermitTypeCode,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY Days) OVER (PARTITION BY PermitTypeCode) AS MedianDays,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY Days) OVER (PARTITION BY PermitTypeCode) AS P90Days
    FROM x
)
SELECT
    x.PermitTypeCode,
    MAX(x.TargetDays)                                                      AS TargetDays,
    COUNT(*)                                                               AS IssuedCount,
    SUM(x.Days)                                                            AS TotalDays,
    CAST(ROUND(AVG(CAST(x.Days AS decimal(10,2))), 1) AS decimal(9,1))     AS AvgDays,
    CAST(ROUND(MAX(pct.MedianDays), 1) AS decimal(9,1))                    AS MedianDays,
    CAST(ROUND(MAX(pct.P90Days), 1) AS decimal(9,1))                       AS P90Days,
    SUM(CASE WHEN x.Days <= x.TargetDays THEN 1 ELSE 0 END)                AS WithinTargetCount
FROM x
JOIN pct ON pct.PermitTypeCode = x.PermitTypeCode
GROUP BY x.PermitTypeCode
ORDER BY x.PermitTypeCode;
