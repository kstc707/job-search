SELECT COUNT(*) AS FeeCount,
       ISNULL(SUM(Amount), 0) AS Assessed,
       ISNULL(SUM(IIF(PaidDate <= '{?EndDate}', PaidAmount, 0)), 0) AS Collected,
       ISNULL(SUM(Amount), 0) - ISNULL(SUM(IIF(PaidDate <= '{?EndDate}', PaidAmount, 0)), 0) AS Outstanding
FROM dbo.Fee
WHERE IsVoided = 0
  AND AssessedDate BETWEEN '{?StartDate}' AND '{?EndDate}'
  AND PermitId IN (
      SELECT PermitId FROM dbo.Permit
      WHERE DistrictId IN (SELECT DistrictId FROM dbo.District WHERE '{?District}' IN ('ALL', DistrictCode))
        AND '{?Status}' IN ('ALL', Status));
