SELECT COUNT(*) AS FeeCount, ISNULL(SUM(Amount - PaidAsOf), 0) AS Balance
FROM (
    SELECT Amount, IIF(PaidDate <= '{?EndDate}', PaidAmount, 0) AS PaidAsOf
    FROM dbo.Fee
    WHERE IsVoided = 0
      AND AssessedDate BETWEEN '{?StartDate}' AND '{?EndDate}'
      AND PermitId IN (
          SELECT PermitId FROM dbo.Permit
          WHERE DistrictId IN (SELECT DistrictId FROM dbo.District WHERE '{?District}' IN ('ALL', DistrictCode))
            AND '{?Status}' IN ('ALL', Status))
) f
WHERE Amount - PaidAsOf > 0;
