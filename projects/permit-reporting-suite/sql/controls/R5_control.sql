SELECT COUNT(*) AS IssuedCount,
       ISNULL(SUM(Days), 0) AS TotalDays,
       COUNT(IIF(Days <= TargetDays, 1, NULL)) AS WithinTargetCount
FROM (
    SELECT DATEDIFF(day, p.AppliedDate, p.IssuedDate) AS Days,
           (SELECT t.TargetDays FROM dbo.PermitType t WHERE t.PermitTypeId = p.PermitTypeId) AS TargetDays
    FROM dbo.Permit p
    WHERE p.IssuedDate IS NOT NULL
      AND p.AppliedDate BETWEEN '{?StartDate}' AND '{?EndDate}'
      AND p.DistrictId IN (SELECT DistrictId FROM dbo.District WHERE '{?District}' IN ('ALL', DistrictCode))
      AND '{?Status}' IN ('ALL', p.Status)
) x;
