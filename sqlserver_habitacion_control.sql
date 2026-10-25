/*
  Cat?logo mantenible habitaci?n/cama -> marca del control requerido.
  Ejecutar en SQL Server Management Studio, base PrestamosCES.
  Fuente: cat?logo transcrito de las dos im?genes suministradas.
  No inventa seriales ni c?digos individuales de controles.
*/
IF DB_ID(N'PrestamosCES') IS NULL
    CREATE DATABASE [PrestamosCES];
GO
USE [PrestamosCES];
GO

IF OBJECT_ID(N'dbo.Controles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Controles
    (
        ControlId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Controles PRIMARY KEY,
        CodigoInventario NVARCHAR(50) NULL,
        Serial NVARCHAR(80) NULL,
        HabitacionId INT NULL,
        Marca NVARCHAR(30) NOT NULL,
        Estado NVARCHAR(20) NOT NULL CONSTRAINT DF_Controles_Estado DEFAULT N'DISPONIBLE',
        Activo BIT NOT NULL CONSTRAINT DF_Controles_Activo DEFAULT 1
    );
END;
GO

IF OBJECT_ID(N'dbo.HabitacionControl', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.HabitacionControl
    (
        UbicacionCodigo NVARCHAR(30) NOT NULL CONSTRAINT PK_HabitacionControl PRIMARY KEY,
        Servicio NVARCHAR(30) NOT NULL,
        Piso NVARCHAR(10) NOT NULL,
        Torre NVARCHAR(20) NULL,
        Habitacion NVARCHAR(30) NOT NULL,
        Cama NVARCHAR(20) NULL,
        MarcaControlRequerida NVARCHAR(20) NOT NULL,
        Activa BIT NOT NULL CONSTRAINT DF_HabitacionControl_Activa DEFAULT 1,
        UpdatedAt DATETIME2 NOT NULL CONSTRAINT DF_HabitacionControl_UpdatedAt DEFAULT SYSUTCDATETIME()
    );
END;
GO

MERGE dbo.HabitacionControl AS destino
USING (VALUES
        (N'301', N'3T3', N'3', N'3', N'301', NULL, N'SONY'),
        (N'302', N'3T3', N'3', N'3', N'302', NULL, N'SONY'),
        (N'303', N'3T3', N'3', N'3', N'303', NULL, N'SONY'),
        (N'304', N'3T3', N'3', N'3', N'304', NULL, N'SONY'),
        (N'305', N'3T3', N'3', N'3', N'305', NULL, N'SAMSUNG'),
        (N'306', N'3T3', N'3', N'3', N'306', NULL, N'SONY'),
        (N'307', N'3T3', N'3', N'3', N'307', NULL, N'PANASONIC'),
        (N'308-1', N'3T3', N'3', N'3', N'308', N'1', N'SAMSUNG'),
        (N'308-2', N'3T3', N'3', N'3', N'308', N'2', N'SONY'),
        (N'309-1', N'3T3', N'3', N'3', N'309', N'1', N'KALLEY'),
        (N'309-2', N'3T3', N'3', N'3', N'309', N'2', N'SAMSUNG'),
        (N'310-1', N'3T3', N'3', N'3', N'310', N'1', N'SONY'),
        (N'310-2', N'3T3', N'3', N'3', N'310', N'2', N'KALLEY'),
        (N'311-1', N'3T3', N'3', N'3', N'311', N'1', N'SONY'),
        (N'311-2', N'3T3', N'3', N'3', N'311', N'2', N'PANASONIC'),
        (N'312', N'3T3', N'3', N'3', N'312', NULL, N'SONY'),
        (N'313', N'3T3', N'3', N'3', N'313', NULL, N'SONY'),
        (N'315', N'3T3', N'3', N'3', N'315', NULL, N'KALLEY'),
        (N'316', N'3T3', N'3', N'3', N'316', NULL, N'SONY'),
        (N'317-1', N'3T3', N'3', N'3', N'317', N'1', N'KALLEY'),
        (N'317-2', N'3T3', N'3', N'3', N'317', N'2', N'KALLEY'),
        (N'318', N'3T3', N'3', N'3', N'318', NULL, N'SONY'),
        (N'319', N'3T3', N'3', N'3', N'319', NULL, N'SAMSUNG'),
        (N'320', N'3T3', N'3', N'3', N'320', NULL, N'PANASONIC'),
        (N'321', N'3T3', N'3', N'3', N'321', NULL, N'SONY'),
        (N'322', N'3T3', N'3', N'3', N'322', NULL, N'SAMSUNG'),
        (N'323', N'3T3', N'3', N'3', N'323', NULL, N'SONY'),
        (N'324', N'3T3', N'3', N'3', N'324', NULL, N'KALLEY'),
        (N'325', N'3T3', N'3', N'3', N'325', NULL, N'SAMSUNG'),
        (N'326-1', N'3T3', N'3', N'3', N'326', N'1', N'SONY'),
        (N'326-2', N'3T3', N'3', N'3', N'326', N'2', N'SONY'),
        (N'327-1', N'3T3', N'3', N'3', N'327', N'1', N'LG'),
        (N'327-2', N'3T3', N'3', N'3', N'327', N'2', N'LG'),
        (N'328-1', N'3T3', N'3', N'3', N'328', N'1', N'SAMSUNG'),
        (N'328-2', N'3T3', N'3', N'3', N'328', N'2', N'SAMSUNG'),
        (N'329-1', N'3T3', N'3', N'3', N'329', N'1', N'SONY'),
        (N'329-2', N'3T3', N'3', N'3', N'329', N'2', N'SONY'),
        (N'330-1', N'3T3', N'3', N'3', N'330', N'1', N'SONY'),
        (N'330-2', N'3T3', N'3', N'3', N'330', N'2', N'SONY'),
        (N'331-1', N'3T3', N'3', N'3', N'331', N'1', N'SONY'),
        (N'331-2', N'3T3', N'3', N'3', N'331', N'2', N'SONY'),
        (N'332-1', N'3T3', N'3', N'3', N'332', N'1', N'SONY'),
        (N'332-2', N'3T3', N'3', N'3', N'332', N'2', N'SONY'),
        (N'333-1', N'3T3', N'3', N'3', N'333', N'1', N'KALLEY'),
        (N'333-2', N'3T3', N'3', N'3', N'333', N'2', N'KALLEY'),
        (N'334', N'3T3', N'3', N'3', N'334', NULL, N'SONY'),
        (N'335-1', N'3T3', N'3', N'3', N'335', N'1', N'PANASONIC'),
        (N'335-2', N'3T3', N'3', N'3', N'335', N'2', N'PANASONIC'),
        (N'336-1', N'3T3', N'3', N'3', N'336', N'1', N'SONY'),
        (N'336-2', N'3T3', N'3', N'3', N'336', N'2', N'SONY'),
        (N'337-1', N'3T3', N'3', N'3', N'337', N'1', N'SAMSUNG'),
        (N'337-2', N'3T3', N'3', N'3', N'337', N'2', N'SAMSUNG'),
        (N'338-1', N'3T3', N'3', N'3', N'338', N'1', N'SONY'),
        (N'338-2', N'3T3', N'3', N'3', N'338', N'2', N'SONY'),
        (N'339-1', N'3T3', N'3', N'3', N'339', N'1', N'SONY'),
        (N'339-2', N'3T3', N'3', N'3', N'339', N'2', N'SONY'),
        (N'340-1', N'3T3', N'3', N'3', N'340', N'1', N'SONY'),
        (N'340-2', N'3T3', N'3', N'3', N'340', N'2', N'SONY'),
        (N'341-1', N'3T3', N'3', N'3', N'341', N'1', N'SONY'),
        (N'341-2', N'3T3', N'3', N'3', N'341', N'2', N'SONY'),
        (N'342', N'3T3', N'3', N'3', N'342', NULL, N'SAMSUNG'),
        (N'343', N'3T3', N'3', N'3', N'343', NULL, N'SONY'),
        (N'344', N'3T3', N'3', N'3', N'344', NULL, N'SAMSUNG'),
        (N'345', N'3T3', N'3', N'3', N'345', NULL, N'SONY'),
        (N'346', N'3T3', N'3', N'3', N'346', NULL, N'SAMSUNG'),
        (N'347', N'3T3', N'3', N'3', N'347', NULL, N'SONY'),
        (N'401-1', N'4T1', N'4', N'1', N'401', N'1', N'SONY'),
        (N'401-2', N'4T1', N'4', N'1', N'401', N'2', N'SONY'),
        (N'402-1', N'4T1', N'4', N'1', N'402', N'1', N'LG'),
        (N'402-2', N'4T1', N'4', N'1', N'402', N'2', N'SONY'),
        (N'403-1', N'4T1', N'4', N'1', N'403', N'1', N'SONY'),
        (N'403-2', N'4T1', N'4', N'1', N'403', N'2', N'SONY'),
        (N'404-1', N'4T1', N'4', N'1', N'404', N'1', N'SONY'),
        (N'404-2', N'4T1', N'4', N'1', N'404', N'2', N'SONY'),
        (N'405', N'4T1', N'4', N'1', N'405', NULL, N'SONY'),
        (N'406', N'4T1', N'4', N'1', N'406', NULL, N'SONY'),
        (N'407', N'4T1', N'4', N'1', N'407', NULL, N'SONY'),
        (N'408', N'4T1', N'4', N'1', N'408', NULL, N'PANASONIC'),
        (N'409', N'4T1', N'4', N'1', N'409', NULL, N'KALLEY'),
        (N'410', N'4T1', N'4', N'1', N'410', NULL, N'SONY'),
        (N'411', N'4T1', N'4', N'1', N'411', NULL, N'SONY'),
        (N'412-1', N'4T1', N'4', N'1', N'412', N'1', N'PANASONIC'),
        (N'412-2', N'4T1', N'4', N'1', N'412', N'2', N'SONY'),
        (N'413-1', N'4T1', N'4', N'1', N'413', N'1', N'SONY'),
        (N'413-2', N'4T1', N'4', N'1', N'413', N'2', N'SONY'),
        (N'414-1', N'4T1', N'4', N'1', N'414', N'1', N'PANASONIC'),
        (N'414-2', N'4T1', N'4', N'1', N'414', N'2', N'SONY'),
        (N'415-1', N'4T1', N'4', N'1', N'415', N'1', N'SAMSUNG'),
        (N'415-2', N'4T1', N'4', N'1', N'415', N'2', N'KALLEY'),
        (N'416-1', N'4T1', N'4', N'1', N'416', N'1', N'SONY'),
        (N'416-2', N'4T1', N'4', N'1', N'416', N'2', N'SONY'),
        (N'417-1', N'4T1', N'4', N'1', N'417', N'1', N'PANASONIC'),
        (N'417-2', N'4T1', N'4', N'1', N'417', N'2', N'PANASONIC'),
        (N'418', N'4T1', N'4', N'1', N'418', NULL, N'SAMSUNG'),
        (N'419', N'4T1', N'4', N'1', N'419', NULL, N'KALLEY'),
        (N'420', N'4T1', N'4', N'1', N'420', NULL, N'SONY'),
        (N'421', N'4T1', N'4', N'1', N'421', NULL, N'SONY'),
        (N'4221', N'4T1', N'4', N'1', N'422', N'1', N'SONY'),
        (N'4222', N'4T1', N'4', N'1', N'422', N'2', N'SONY'),
        (N'4231', N'4T1', N'4', N'1', N'423', N'1', N'SONY'),
        (N'4232', N'4T1', N'4', N'1', N'423', N'2', N'SONY'),
        (N'4241', N'4T1', N'4', N'1', N'424', N'1', N'KALLEY'),
        (N'4242', N'4T1', N'4', N'1', N'424', N'2', N'KALLEY'),
        (N'4251', N'4T1', N'4', N'1', N'425', N'1', N'SONY'),
        (N'4252', N'4T1', N'4', N'1', N'425', N'2', N'SONY'),
        (N'426', N'4T1', N'4', N'1', N'426', NULL, N'SONY'),
        (N'4271', N'4T1', N'4', N'1', N'427', N'1', N'SONY'),
        (N'4272', N'4T1', N'4', N'1', N'427', N'2', N'SONY'),
        (N'4281', N'4T1', N'4', N'1', N'428', N'1', N'SAMSUNG'),
        (N'4282', N'4T1', N'4', N'1', N'428', N'2', N'SAMSUNG'),
        (N'4291', N'4T1', N'4', N'1', N'429', N'1', N'KALLEY'),
        (N'4292', N'4T1', N'4', N'1', N'429', N'2', N'KALLEY'),
        (N'4301', N'4T1', N'4', N'1', N'430', N'1', N'LG'),
        (N'4302', N'4T1', N'4', N'1', N'430', N'2', N'LG'),
        (N'4311', N'4T1', N'4', N'1', N'431', N'1', N'SONY'),
        (N'4312', N'4T1', N'4', N'1', N'431', N'2', N'SONY'),
        (N'4322', N'4T1', N'4', N'1', N'432', N'2', N'SONY'),
        (N'4331', N'4T1', N'4', N'1', N'433', N'1', N'SAMSUNG'),
        (N'4332', N'4T1', N'4', N'1', N'433', N'2', N'SAMSUNG'),
        (N'4341', N'4T2', N'4', N'2', N'434', N'1', N'SONY'),
        (N'4342', N'4T2', N'4', N'2', N'434', N'2', N'SONY'),
        (N'4343', N'4T2', N'4', N'2', N'434', N'3', N'SONY'),
        (N'4351', N'4T2', N'4', N'2', N'435', N'1', N'SONY'),
        (N'4352', N'4T2', N'4', N'2', N'435', N'2', N'SONY'),
        (N'4353', N'4T2', N'4', N'2', N'435', N'3', N'SONY'),
        (N'4361', N'4T2', N'4', N'2', N'436', N'1', N'SONY'),
        (N'4362', N'4T2', N'4', N'2', N'436', N'2', N'SONY'),
        (N'4363', N'4T2', N'4', N'2', N'436', N'3', N'SONY'),
        (N'4371', N'4T2', N'4', N'2', N'437', N'1', N'SONY'),
        (N'4372', N'4T2', N'4', N'2', N'437', N'2', N'SONY'),
        (N'4373', N'4T2', N'4', N'2', N'437', N'3', N'SONY'),
        (N'4381', N'4T2', N'4', N'2', N'438', N'1', N'SONY'),
        (N'4382', N'4T2', N'4', N'2', N'438', N'2', N'SONY'),
        (N'4383', N'4T2', N'4', N'2', N'438', N'3', N'SONY'),
        (N'4391', N'4T2', N'4', N'2', N'439', N'1', N'SONY'),
        (N'4392', N'4T2', N'4', N'2', N'439', N'2', N'SONY'),
        (N'4393', N'4T2', N'4', N'2', N'439', N'3', N'SONY'),
        (N'501', N'5T3', N'5', N'3', N'501', NULL, N'SONY'),
        (N'502', N'5T3', N'5', N'3', N'502', NULL, N'SONY'),
        (N'503', N'5T3', N'5', N'3', N'503', NULL, N'SAMSUNG'),
        (N'504', N'5T3', N'5', N'3', N'504', NULL, N'SAMSUNG'),
        (N'505', N'5T3', N'5', N'3', N'505', NULL, N'SAMSUNG'),
        (N'506', N'5T3', N'5', N'3', N'506', NULL, N'SAMSUNG'),
        (N'507', N'5T3', N'5', N'3', N'507', NULL, N'SAMSUNG'),
        (N'508', N'5T3', N'5', N'3', N'508', NULL, N'SONY'),
        (N'509', N'5T3', N'5', N'3', N'509', NULL, N'KALLEY'),
        (N'510', N'5T3', N'5', N'3', N'510', NULL, N'SONY'),
        (N'5111', N'5T3', N'5', N'3', N'511', N'1', N'SONY'),
        (N'5112', N'5T3', N'5', N'3', N'511', N'2', N'KALLEY'),
        (N'512', N'5T3', N'5', N'3', N'512', NULL, N'SAMSUNG'),
        (N'513', N'5T3', N'5', N'3', N'513', NULL, N'SONY'),
        (N'514', N'5T3', N'5', N'3', N'514', NULL, N'SONY'),
        (N'515', N'5T3', N'5', N'3', N'515', NULL, N'SONY'),
        (N'516', N'5T3', N'5', N'3', N'516', NULL, N'SAMSUNG'),
        (N'517', N'5T3', N'5', N'3', N'517', NULL, N'KALLEY'),
        (N'UCE-1', N'6T3', N'6', N'3', N'UCE', N'1', N'SAMSUNG'),
        (N'UCE-2', N'6T3', N'6', N'3', N'UCE', N'2', N'SONY'),
        (N'UCE-3', N'6T3', N'6', N'3', N'UCE', N'3', N'PANASONIC'),
        (N'UCE-4', N'6T3', N'6', N'3', N'UCE', N'4', N'SONY'),
        (N'UCE-5', N'6T3', N'6', N'3', N'UCE', N'5', N'SONY'),
        (N'UCE-6', N'6T3', N'6', N'3', N'UCE', N'6', N'LG'),
        (N'UCE-7', N'6T3', N'6', N'3', N'UCE', N'7', N'PANASONIC'),
        (N'UCE-8', N'6T3', N'6', N'3', N'UCE', N'8', N'KALLEY'),
        (N'UCE-9', N'6T3', N'6', N'3', N'UCE', N'9', N'SONY'),
        (N'UCE-10', N'6T3', N'6', N'3', N'UCE', N'10', N'SAMSUNG'),
        (N'UCE-11', N'6T3', N'6', N'3', N'UCE', N'11', N'SAMSUNG'),
        (N'UCE-12', N'6T3', N'6', N'3', N'UCE', N'12', N'SAMSUNG'),
        (N'UCE-13', N'6T3', N'6', N'3', N'UCE', N'13', N'SAMSUNG'),
        (N'UCE-14', N'6T3', N'6', N'3', N'UCE', N'14', N'SAMSUNG'),
        (N'UCE-15', N'6T3', N'6', N'3', N'UCE', N'15', N'SAMSUNG'),
        (N'UCE-16', N'6T3', N'6', N'3', N'UCE', N'16', N'SAMSUNG'),
        (N'UCE-17', N'6T3', N'6', N'3', N'UCE', N'17', N'PANASONIC'),
        (N'UCE-18', N'6T3', N'6', N'3', N'UCE', N'18', N'SAMSUNG'),
        (N'UCE-19', N'6T3', N'6', N'3', N'UCE', N'19', N'SONY'),
        (N'UCE-23', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'23', N'SAMSUNG'),
        (N'UCE-24', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'24', N'SAMSUNG'),
        (N'UCE-25', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'25', N'SAMSUNG'),
        (N'UCE-26', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'26', N'SONY'),
        (N'UCE-27', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'27', N'SAMSUNG'),
        (N'UCE-28', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'28', N'SAMSUNG'),
        (N'UCE-29', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'29', N'SAMSUNG'),
        (N'UCE-30', N'UCE-PISO 5', N'5', N'3', N'UCE-PISO 5', N'30', N'SAMSUNG')
) AS origen(UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama, MarcaControlRequerida)
ON destino.UbicacionCodigo = origen.UbicacionCodigo
WHEN MATCHED THEN UPDATE SET
    Servicio=origen.Servicio, Piso=origen.Piso, Torre=origen.Torre,
    Habitacion=origen.Habitacion, Cama=origen.Cama,
    MarcaControlRequerida=origen.MarcaControlRequerida, Activa=1,
    UpdatedAt=SYSUTCDATETIME()
WHEN NOT MATCHED BY TARGET THEN INSERT
    (UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama, MarcaControlRequerida, Activa, UpdatedAt)
    VALUES (origen.UbicacionCodigo, origen.Servicio, origen.Piso, origen.Torre,
            origen.Habitacion, origen.Cama, origen.MarcaControlRequerida, 1, SYSUTCDATETIME());
GO

IF OBJECT_ID(N'dbo.Controles', N'U') IS NOT NULL
    EXEC(N'CREATE OR ALTER VIEW dbo.vw_ControlesDisponiblesPorHabitacion AS
        SELECT m.UbicacionCodigo, m.Servicio, m.Piso, m.Habitacion, m.Cama,
               m.MarcaControlRequerida, c.ControlId, c.CodigoInventario, c.Serial,
               c.Marca AS MarcaControl, c.Estado
          FROM dbo.HabitacionControl AS m
          LEFT JOIN dbo.Controles AS c
            ON c.Activo=1 AND c.Estado=N''DISPONIBLE''
           AND UPPER(LTRIM(RTRIM(c.Marca)))=UPPER(LTRIM(RTRIM(m.MarcaControlRequerida)))
         WHERE m.Activa=1;');
GO

/* Comprobaci?n: debe mostrar la relaci?n 301 -> SONY y el stock SONY disponible. */
SELECT UbicacionCodigo, Servicio, Piso, Habitacion, Cama,
       MarcaControlRequerida, ControlId, CodigoInventario, Serial, MarcaControl, Estado
FROM dbo.vw_ControlesDisponiblesPorHabitacion
WHERE UbicacionCodigo=N'301'
ORDER BY CodigoInventario, Serial;
GO
