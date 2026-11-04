SELECT COUNT(*) AS Assigned,
       COUNT(IIF(Result IN ('Pass','Fail','Partial'), 1, NULL)) AS Completed,
       COUNT(IIF(Result = 'Pass', 1, NULL))     AS Passed,
       COUNT(IIF(Result = 'Fail', 1, NULL))     AS Failed,
       COUNT(IIF(Result = 'Canceled', 1, NULL)) AS Canceled
FROM dbo.Inspection
WHERE ScheduledDate BETWEEN '{?StartDate}' AND '{?EndDate}'
  AND PermitId IN (
      SELECT PermitId FROM dbo.Permit
      WHERE DistrictId IN (SELECT DistrictId FROM dbo.District WHERE '{?District}' IN ('ALL', DistrictCode))
        AND '{?Status}' IN ('ALL', Status));
