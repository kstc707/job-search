-- R3 Outstanding Fee Aging, as of EndDate.
-- Fees assessed in the date range, not voided, with a balance left on EndDate.
-- Bucket = days past DueDate on EndDate.
WITH bal AS (
    SELECT
        d.DistrictCode,
        f.Amount - CASE WHEN f.PaidDate < DATEADD(day, 1, CAST('{?EndDate}' AS date))
                        THEN f.PaidAmount ELSE 0 END                 AS Balance,
        DATEDIFF(day, f.DueDate, CAST('{?EndDate}' AS date))        AS DaysPastDue
    FROM dbo.Fee f
    JOIN dbo.Permit   p ON p.PermitId   = f.PermitId
    JOIN dbo.District d ON d.DistrictId = p.DistrictId
    WHERE f.IsVoided = 0
      AND f.AssessedDate >= CAST('{?StartDate}' AS date)
      AND f.AssessedDate <  DATEADD(day, 1, CAST('{?EndDate}' AS date))
      AND ('{?District}' = 'ALL' OR d.DistrictCode = '{?District}')
      AND ('{?Status}'   = 'ALL' OR p.Status       = '{?Status}')
)
SELECT
    DistrictCode,
    CASE WHEN DaysPastDue <= 0  THEN '0 Current'
         WHEN DaysPastDue <= 30 THEN '1 1-30'
         WHEN DaysPastDue <= 60 THEN '2 31-60'
         WHEN DaysPastDue <= 90 THEN '3 61-90'
         ELSE '4 90+' END                                            AS AgingBucket,
    COUNT(*)                                                         AS FeeCount,
    SUM(Balance)                                                     AS Balance
FROM bal
WHERE Balance > 0
GROUP BY DistrictCode,
    CASE WHEN DaysPastDue <= 0  THEN '0 Current'
         WHEN DaysPastDue <= 30 THEN '1 1-30'
         WHEN DaysPastDue <= 60 THEN '2 31-60'
         WHEN DaysPastDue <= 90 THEN '3 61-90'
         ELSE '4 90+' END
ORDER BY DistrictCode, AgingBucket;
