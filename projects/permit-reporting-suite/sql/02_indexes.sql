-- Indexes that let the SQL Commands seek on the report date and read every column they need
-- from the index (covering), instead of scanning the clustered table.

CREATE NONCLUSTERED INDEX IX_Permit_AppliedDate
    ON dbo.Permit (AppliedDate)
    INCLUDE (DistrictId, PermitTypeId, Status, Valuation, IssuedDate);

CREATE NONCLUSTERED INDEX IX_Fee_AssessedDate
    ON dbo.Fee (AssessedDate)
    INCLUDE (PermitId, FeeTypeId, DueDate, Amount, PaidAmount, PaidDate, IsVoided);

CREATE NONCLUSTERED INDEX IX_Inspection_ScheduledDate
    ON dbo.Inspection (ScheduledDate)
    INCLUDE (PermitId, InspectionTypeId, InspectorId, Result);

CREATE NONCLUSTERED INDEX IX_Fee_PermitId ON dbo.Fee (PermitId);
CREATE NONCLUSTERED INDEX IX_Inspection_PermitId ON dbo.Inspection (PermitId);
GO
