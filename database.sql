/*
  Base de datos de prueba para el sistema de préstamo de controles.
  Ejecutar este archivo completo en SQL Server Management Studio 22.
*/

IF DB_ID(N'PrestamosCES') IS NULL
BEGIN
    CREATE DATABASE PrestamosCES;
END;
GO

USE PrestamosCES;
GO

/* Tabla de usuarios que pueden iniciar sesión en la aplicación. */
IF OBJECT_ID(N'dbo.Usuarios', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Usuarios
    (
        UsuarioId INT IDENTITY(1,1) CONSTRAINT PK_Usuarios PRIMARY KEY,
        Usuario NVARCHAR(50) NOT NULL CONSTRAINT UQ_Usuarios_Usuario UNIQUE,
        Cedula NVARCHAR(20) NOT NULL CONSTRAINT UQ_Usuarios_Cedula UNIQUE,
        Contrasena NVARCHAR(150) NOT NULL,
        Rol NVARCHAR(30) NOT NULL CONSTRAINT DF_Usuarios_Rol DEFAULT N'Enfermeria',
        Activo BIT NOT NULL CONSTRAINT DF_Usuarios_Activo DEFAULT 1
    );
END;
GO

/* Habitaciones disponibles y su piso dentro de la clínica. */
IF OBJECT_ID(N'dbo.Habitaciones', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Habitaciones
    (
        HabitacionId INT IDENTITY(1,1) CONSTRAINT PK_Habitaciones PRIMARY KEY,
        Numero NVARCHAR(30) NOT NULL CONSTRAINT UQ_Habitaciones_Numero UNIQUE,
        Piso NVARCHAR(10) NOT NULL,
        Servicio NVARCHAR(30) NULL,
        Torre NVARCHAR(20) NULL,
        Habitacion NVARCHAR(30) NULL,
        Cama NVARCHAR(20) NULL,
        UbicacionCodigo NVARCHAR(30) NULL,
        MarcaControlRequerida NVARCHAR(20) NULL,
        CreatedAt DATETIME2 NULL,
        UpdatedAt DATETIME2 NULL,
        Activa BIT NOT NULL CONSTRAINT DF_Habitaciones_Activa DEFAULT 1
    );
END;
GO

IF COL_LENGTH('dbo.Habitaciones', 'Torre') IS NULL ALTER TABLE dbo.Habitaciones ADD Torre NVARCHAR(20) NULL;
IF COL_LENGTH('dbo.Habitaciones', 'Habitacion') IS NULL ALTER TABLE dbo.Habitaciones ADD Habitacion NVARCHAR(30) NULL;
IF COL_LENGTH('dbo.Habitaciones', 'Cama') IS NULL ALTER TABLE dbo.Habitaciones ADD Cama NVARCHAR(20) NULL;
IF COL_LENGTH('dbo.Habitaciones', 'UbicacionCodigo') IS NULL ALTER TABLE dbo.Habitaciones ADD UbicacionCodigo NVARCHAR(30) NULL;
IF COL_LENGTH('dbo.Habitaciones', 'MarcaControlRequerida') IS NULL ALTER TABLE dbo.Habitaciones ADD MarcaControlRequerida NVARCHAR(20) NULL;
IF COL_LENGTH('dbo.Habitaciones', 'CreatedAt') IS NULL ALTER TABLE dbo.Habitaciones ADD CreatedAt DATETIME2 NULL;
IF COL_LENGTH('dbo.Habitaciones', 'UpdatedAt') IS NULL ALTER TABLE dbo.Habitaciones ADD UpdatedAt DATETIME2 NULL;
GO

/* Controles remotos registrados por habitación. */
IF OBJECT_ID(N'dbo.Controles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Controles
    (
        ControlId INT IDENTITY(1,1) CONSTRAINT PK_Controles PRIMARY KEY,
        CodigoInventario NVARCHAR(50) NULL,
        Serial NVARCHAR(80) NULL,
        HabitacionId INT NULL,
        Marca NVARCHAR(30) NOT NULL,
        Estado NVARCHAR(20) NOT NULL CONSTRAINT DF_Controles_Estado DEFAULT N'SIN_VERIFICAR',
        Activo BIT NOT NULL CONSTRAINT DF_Controles_Activo DEFAULT 1,
        CONSTRAINT FK_Controles_Habitaciones FOREIGN KEY (HabitacionId)
            REFERENCES dbo.Habitaciones(HabitacionId),
        CONSTRAINT CK_Controles_Estado CHECK (Estado IN (N'DISPONIBLE', N'PRESTADO', N'FUERA_SERVICIO', N'SIN_VERIFICAR'))
    );
END;
GO

IF COL_LENGTH('dbo.Controles', 'CodigoInventario') IS NULL ALTER TABLE dbo.Controles ADD CodigoInventario NVARCHAR(50) NULL;
IF COL_LENGTH('dbo.Controles', 'Serial') IS NULL ALTER TABLE dbo.Controles ADD Serial NVARCHAR(80) NULL;
IF COL_LENGTH('dbo.Controles', 'Estado') IS NULL
    ALTER TABLE dbo.Controles ADD Estado NVARCHAR(20) NOT NULL
        CONSTRAINT DF_Controles_Estado_Migracion DEFAULT N'SIN_VERIFICAR' WITH VALUES;
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_Controles_Estado')
    ALTER TABLE dbo.Controles ADD CONSTRAINT CK_Controles_Estado
        CHECK (Estado IN (N'DISPONIBLE',N'PRESTADO',N'FUERA_SERVICIO',N'SIN_VERIFICAR'));
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Habitaciones_ServicioUbicacion' AND object_id = OBJECT_ID(N'dbo.Habitaciones'))
    CREATE UNIQUE INDEX UX_Habitaciones_ServicioUbicacion ON dbo.Habitaciones(Servicio, UbicacionCodigo) WHERE Servicio IS NOT NULL AND UbicacionCodigo IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Controles_CodigoInventario' AND object_id = OBJECT_ID(N'dbo.Controles'))
    CREATE UNIQUE INDEX UX_Controles_CodigoInventario ON dbo.Controles(CodigoInventario) WHERE CodigoInventario IS NOT NULL;
GO

/* Diez pacientes ficticios, todos hospitalizados para las pruebas. */
IF OBJECT_ID(N'dbo.Pacientes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Pacientes
    (
        PacienteId INT IDENTITY(1,1) CONSTRAINT PK_Pacientes PRIMARY KEY,
        Cedula NVARCHAR(20) NOT NULL CONSTRAINT UQ_Pacientes_Cedula UNIQUE,
        Nombre NVARCHAR(60) NOT NULL,
        Apellido NVARCHAR(60) NOT NULL,
        HabitacionId INT NOT NULL,
        Estado NVARCHAR(30) NOT NULL CONSTRAINT DF_Pacientes_Estado DEFAULT N'Hospitalizado',
        FechaIngreso DATE NOT NULL CONSTRAINT DF_Pacientes_FechaIngreso DEFAULT CONVERT(DATE, GETDATE()),
        CONSTRAINT FK_Pacientes_Habitaciones FOREIGN KEY (HabitacionId)
            REFERENCES dbo.Habitaciones(HabitacionId)
    );
END;
GO

/* Historial de entregas y devoluciones de controles. */
IF OBJECT_ID(N'dbo.Prestamos', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Prestamos
    (
        PrestamoId INT IDENTITY(1,1) CONSTRAINT PK_Prestamos PRIMARY KEY,
        PacienteId INT NOT NULL,
        ControlId INT NOT NULL,
        UsuarioEntregaId INT NOT NULL,
        FechaEntrega DATE NOT NULL CONSTRAINT DF_Prestamos_FechaEntrega DEFAULT CONVERT(DATE, GETDATE()),
        FechaDevolucion DATE NULL,
        Dias INT NOT NULL CONSTRAINT CK_Prestamos_Dias CHECK (Dias >= 0),
        Total DECIMAL(12,2) NOT NULL CONSTRAINT CK_Prestamos_Total CHECK (Total >= 0),
        CONSTRAINT FK_Prestamos_Pacientes FOREIGN KEY (PacienteId) REFERENCES dbo.Pacientes(PacienteId),
        CONSTRAINT FK_Prestamos_Controles FOREIGN KEY (ControlId) REFERENCES dbo.Controles(ControlId),
        CONSTRAINT FK_Prestamos_Usuarios FOREIGN KEY (UsuarioEntregaId) REFERENCES dbo.Usuarios(UsuarioId)
    );
END;
GO

/* Usuarios de prueba: las claves coinciden con app.py. */
IF NOT EXISTS (SELECT 1 FROM dbo.Usuarios WHERE Usuario = N'admin')
BEGIN
    INSERT INTO dbo.Usuarios (Usuario, Cedula, Contrasena, Rol)
    VALUES
        (N'admin', N'1001', N'admin1232026*', N'Administrador'),
        (N'usuario1', N'1002', N'usuario1232026*', N'Usuario'),
        (N'usuario2', N'1003', N'usuario4562026*', N'Usuario'),
        (N'enfermeria', N'1004', N'enfermeria1232026*', N'Enfermeria');
END;
GO

/* Habitaciones de prueba tomadas del listado de la clínica. */
INSERT INTO dbo.Habitaciones (Numero, Piso)
SELECT datos.Numero, datos.Piso
FROM (VALUES
    (N'301', N'3'), (N'305', N'3'), (N'307', N'3'), (N'309-1', N'3'),
    (N'327-1 Y 2', N'3'), (N'402-1', N'4'), (N'418', N'4'),
    (N'UCE-1', N'UCE'), (N'UCE-3', N'UCE'), (N'UCE-6', N'UCE')
) AS datos(Numero, Piso)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Habitaciones h WHERE h.Numero = datos.Numero);
GO

/* No insertar controles físicos desde el catálogo de ubicaciones. */

/* Diez pacientes ficticios hospitalizados para probar la entrega. */
INSERT INTO dbo.Pacientes (Cedula, Nombre, Apellido, HabitacionId, Estado)
SELECT datos.Cedula, datos.Nombre, datos.Apellido, h.HabitacionId, N'Hospitalizado'
FROM (VALUES
    (N'1100000001', N'Ana', N'Martinez', N'301'),
    (N'1100000002', N'Carlos', N'Rojas', N'305'),
    (N'1100000003', N'Diana', N'Gomez', N'307'),
    (N'1100000004', N'Ernesto', N'Vargas', N'309-1'),
    (N'1100000005', N'Fernanda', N'Lopez', N'327-1 Y 2'),
    (N'1100000006', N'Gabriel', N'Torres', N'402-1'),
    (N'1100000007', N'Helena', N'Castro', N'418'),
    (N'1100000008', N'Iván', N'Moreno', N'UCE-1'),
    (N'1100000009', N'Juliana', N'Silva', N'UCE-3'),
    (N'1100000010', N'Kevin', N'Pineda', N'UCE-6')
) AS datos(Cedula, Nombre, Apellido, NumeroHabitacion)
INNER JOIN dbo.Habitaciones h ON h.Numero = datos.NumeroHabitacion
WHERE NOT EXISTS (SELECT 1 FROM dbo.Pacientes p WHERE p.Cedula = datos.Cedula);
GO

/* Consulta de verificación para revisar los diez pacientes y sus controles. */
SELECT p.Cedula, p.Nombre, p.Apellido, h.Numero AS Habitacion, c.Marca, p.Estado
FROM dbo.Pacientes p
INNER JOIN dbo.Habitaciones h ON h.HabitacionId = p.HabitacionId
LEFT JOIN dbo.Controles c ON c.HabitacionId = h.HabitacionId AND c.Activo = 1
ORDER BY h.Piso, h.Numero;
GO
