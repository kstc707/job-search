SELECT COUNT(*) AS PermitCount,
       ISNULL(SUM(Valuation), 0) AS TotalValuation,
       COUNT(*) - COUNT(Valuation) AS MissingValuationCount
FROM dbo.Permit
WHERE AppliedDate BETWEEN '{?StartDate}' AND '{?EndDate}'
  AND DistrictId IN (SELECT DistrictId FROM dbo.District WHERE '{?District}' IN ('ALL', DistrictCode))
  AND Status IN (SELECT DISTINCT Status FROM dbo.Permit WHERE '{?Status}' IN ('ALL', Status));
