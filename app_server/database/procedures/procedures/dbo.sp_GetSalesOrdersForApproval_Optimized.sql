
-- SP Lấy danh sách Đơn hàng chờ duyệt (Tối ưu hóa)
CREATE PROCEDURE [dbo].[sp_GetSalesOrdersForApproval_Optimized]
    @UserCode NVARCHAR(50),
    @DateFrom DATE,
    @DateTo DATE,
    @IsAdmin BIT
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Lấy danh sách VoucherType mà User có quyền duyệt
    DECLARE @UserPermissions TABLE (VoucherTypeID NVARCHAR(20));
    
    IF @IsAdmin = 0
    BEGIN
        INSERT INTO @UserPermissions (VoucherTypeID)
        SELECT DISTINCT VoucherTypeID 
        FROM [OT0006] 
        WHERE LOWER(Approver) = LOWER(@UserCode);
    END

    -- 2. Truy vấn chính từ bảng Đơn hàng (OT2001)
    SELECT 
        T1.SorderID, T1.VoucherNo, T1.OrderDate AS VoucherDate, 
        T1.SalesManID, T1.EmployeeID, T1.VoucherTypeID,
        T1.ObjectID AS ClientID,
        ISNULL(T2.ShortObjectName, 'N/A') AS ClientName,
        ISNULL(T2.O05ID, 'N/A') AS CustomerClass,
        ISNULL(T7.SHORTNAME, 'N/A') AS NVKDName,
        
        -- Tính tổng giá trị đơn hàng (Từ chi tiết OT2002)
        (SELECT SUM(D.ConvertedAmount) FROM [OMEGA_STDD].[dbo].[OT2002] D WHERE D.SorderID = T1.SorderID) AS TotalSaleAmount,

        -- Lấy danh sách người duyệt
        (
            SELECT STUFF((
                SELECT ', ' + RTRIM(Approver)
                FROM [OT0006] A
                WHERE A.VoucherTypeID = T1.VoucherTypeID
                FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '')
        ) AS ApproverList

    FROM [OMEGA_STDD].[dbo].[OT2001] AS T1
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T2 ON T1.ObjectID = T2.ObjectID
    LEFT JOIN [dbo].[GD - NGUOI DUNG] AS T7 ON T1.SalesManID = T7.USERCODE

    WHERE 
        -- Status: 1=Mới, 2=Chờ duyệt (Điều chỉnh nếu DB dùng 0)
        T1.OrderStatus = 0 
        AND T1.OrderDate BETWEEN @DateFrom AND @DateTo
        
        AND (
            -- Logic Phân quyền (AND)
            (@IsAdmin = 1) -- Admin xem hết
            OR 
            (
                T1.SalesManID = @UserCode -- Chính chủ
                AND
                T1.VoucherTypeID IN (SELECT VoucherTypeID FROM @UserPermissions) -- Có quyền duyệt
            )
        )
    
    ORDER BY T1.OrderDate DESC;
END

GO
