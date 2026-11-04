-- Permit & Inspection Reporting Suite: schema.
-- Run with: python -m permit_reports setup   (splits on GO, creates the database if missing)

IF OBJECT_ID('dbo.Inspection', 'U') IS NOT NULL DROP TABLE dbo.Inspection;
IF OBJECT_ID('dbo.Fee', 'U') IS NOT NULL DROP TABLE dbo.Fee;
IF OBJECT_ID('dbo.Permit', 'U') IS NOT NULL DROP TABLE dbo.Permit;
IF OBJECT_ID('dbo.Inspector', 'U') IS NOT NULL DROP TABLE dbo.Inspector;
IF OBJECT_ID('dbo.InspectionType', 'U') IS NOT NULL DROP TABLE dbo.InspectionType;
IF OBJECT_ID('dbo.FeeType', 'U') IS NOT NULL DROP TABLE dbo.FeeType;
IF OBJECT_ID('dbo.PermitType', 'U') IS NOT NULL DROP TABLE dbo.PermitType;
IF OBJECT_ID('dbo.District', 'U') IS NOT NULL DROP TABLE dbo.District;
GO

-- Lookup tables -------------------------------------------------------------
CREATE TABLE dbo.District (
    DistrictId    int          NOT NULL PRIMARY KEY,
    DistrictCode  varchar(10)  NOT NULL UNIQUE,
    DistrictName  varchar(60)  NOT NULL
);

CREATE TABLE dbo.PermitType (
    PermitTypeId    int          NOT NULL PRIMARY KEY,
    PermitTypeCode  varchar(10)  NOT NULL UNIQUE,
    PermitTypeName  varchar(60)  NOT NULL,
    TargetDays      int          NOT NULL   -- service-level target: applied -> issued
);

CREATE TABLE dbo.FeeType (
    FeeTypeId    int          NOT NULL PRIMARY KEY,
    FeeTypeCode  varchar(10)  NOT NULL UNIQUE,
    FeeTypeName  varchar(60)  NOT NULL
);

CREATE TABLE dbo.InspectionType (
    InspectionTypeId    int          NOT NULL PRIMARY KEY,
    InspectionTypeCode  varchar(10)  NOT NULL UNIQUE,
    InspectionTypeName  varchar(60)  NOT NULL
);

CREATE TABLE dbo.Inspector (
    InspectorId     int          NOT NULL PRIMARY KEY,
    InspectorName   varchar(60)  NOT NULL,
    HomeDistrictId  int          NOT NULL REFERENCES dbo.District (DistrictId)
);
GO

-- Fact tables ---------------------------------------------------------------
CREATE TABLE dbo.Permit (
    PermitId      int            NOT NULL PRIMARY KEY,
    PermitNumber  varchar(20)    NOT NULL UNIQUE,
    PermitTypeId  int            NOT NULL REFERENCES dbo.PermitType (PermitTypeId),
    DistrictId    int            NOT NULL REFERENCES dbo.District (DistrictId),
    Status        varchar(20)    NOT NULL
        CONSTRAINT CK_Permit_Status CHECK (Status IN ('Applied','In Review','Issued','Finaled','Expired','Withdrawn')),
    AppliedDate   date           NOT NULL,
    IssuedDate    date           NULL,
    FinaledDate   date           NULL,
    Valuation     decimal(14,2)  NULL,      -- NULL on purpose for a few rows: tests NULL handling in totals
    CONSTRAINT CK_Permit_Dates CHECK (IssuedDate IS NULL OR IssuedDate >= AppliedDate)
);

CREATE TABLE dbo.Fee (
    FeeId         int            NOT NULL PRIMARY KEY,
    PermitId      int            NOT NULL REFERENCES dbo.Permit (PermitId),
    FeeTypeId     int            NOT NULL REFERENCES dbo.FeeType (FeeTypeId),
    AssessedDate  date           NOT NULL,
    DueDate       date           NOT NULL,
    Amount        decimal(12,2)  NOT NULL CHECK (Amount > 0),
    PaidAmount    decimal(12,2)  NOT NULL DEFAULT 0,
    PaidDate      date           NULL,
    IsVoided      bit            NOT NULL DEFAULT 0,
    CONSTRAINT CK_Fee_Paid CHECK (PaidAmount >= 0 AND PaidAmount <= Amount),
    CONSTRAINT CK_Fee_PaidDate CHECK ((PaidAmount = 0 AND PaidDate IS NULL) OR (PaidAmount > 0 AND PaidDate IS NOT NULL))
);

CREATE TABLE dbo.Inspection (
    InspectionId      int          NOT NULL PRIMARY KEY,
    PermitId          int          NOT NULL REFERENCES dbo.Permit (PermitId),
    InspectionTypeId  int          NOT NULL REFERENCES dbo.InspectionType (InspectionTypeId),
    InspectorId       int          NOT NULL REFERENCES dbo.Inspector (InspectorId),
    ScheduledDate     date         NOT NULL,
    CompletedDate     date         NULL,
    Result            varchar(12)  NOT NULL
        CONSTRAINT CK_Inspection_Result CHECK (Result IN ('Pass','Fail','Partial','Canceled','Pending'))
);
GO
