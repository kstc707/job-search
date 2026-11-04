-- Used by R4 and R6 baselines.
SELECT i.InspectionId, i.PermitId, d.DistrictCode, it.InspectionTypeCode, p.Status,
       ins.InspectorName, hd.DistrictCode AS HomeDistrict, i.ScheduledDate, i.Result
FROM dbo.Inspection i
JOIN dbo.Permit         p   ON p.PermitId          = i.PermitId
JOIN dbo.District       d   ON d.DistrictId        = p.DistrictId
JOIN dbo.InspectionType it  ON it.InspectionTypeId = i.InspectionTypeId
JOIN dbo.Inspector      ins ON ins.InspectorId     = i.InspectorId
JOIN dbo.District       hd  ON hd.DistrictId       = ins.HomeDistrictId;
