-- Used by R1 and R5 baselines.
SELECT p.PermitId, d.DistrictCode, pt.PermitTypeCode, pt.TargetDays, p.Status,
       p.AppliedDate, p.IssuedDate, p.Valuation
FROM dbo.Permit p
JOIN dbo.District   d  ON d.DistrictId    = p.DistrictId
JOIN dbo.PermitType pt ON pt.PermitTypeId = p.PermitTypeId;
