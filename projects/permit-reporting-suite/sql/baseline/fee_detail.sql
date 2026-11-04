-- Used by R2 and R3 baselines.
SELECT f.FeeId, d.DistrictCode, ft.FeeTypeCode, p.Status, f.AssessedDate, f.DueDate,
       f.Amount, f.PaidAmount, f.PaidDate, f.IsVoided
FROM dbo.Fee f
JOIN dbo.Permit   p  ON p.PermitId   = f.PermitId
JOIN dbo.District d  ON d.DistrictId = p.DistrictId
JOIN dbo.FeeType  ft ON ft.FeeTypeId = f.FeeTypeId;
