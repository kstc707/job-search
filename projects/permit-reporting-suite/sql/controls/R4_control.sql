SELECT COUNT(*) AS Scheduled,
       COUNT(IIF(Result = 'Pass', 1, NULL))     AS Passed,
       COUNT(IIF(Result = 'Fail', 1, NULL))     AS Failed,
       COUNT(IIF(Result = 'Partial', 1, NULL))  AS Partial,
       COUNT(IIF(Result = 'Canceled', 1, NULL)) AS Canceled,
       COUNT(IIF(Result = 'Pending', 1, NULL))  AS Pending
FROM dbo.Inspection
WHERE ScheduledDate BETWEEN '{?StartDate}' AND '{?EndDate}'
  AND PermitId IN (
      SELECT PermitId FROM dbo.Permit
      WHERE DistrictId IN (SELECT DistrictId FROM dbo.District WHERE '{?District}' IN ('ALL', DistrictCode))
        AND '{?Status}' IN ('ALL', Status));
