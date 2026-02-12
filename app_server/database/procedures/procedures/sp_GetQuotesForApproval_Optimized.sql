
CREATE PROCEDURE [dbo].[sp_GetQuotesForApproval_Optimized]
    @UserCode NVARCHAR(50),
    @DateFrom DATE,
    @DateTo DATE,
    @IsAdmin BIT
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Lấy danh sách VoucherType mà User có quyền duyệt
    -- (Bảng tạm này giúp tối ưu truy vấn chính)
    DECLARE @UserPermissions TABLE (VoucherTypeID NVARCHAR(20));
    
    -- Chỉ cần lấy quyền nếu không phải Admin
    IF @IsAdmin = 0
    BEGIN
        INSERT INTO @UserPermissions (VoucherTypeID)
        SELECT DISTINCT VoucherTypeID 
        FROM [OT0006] 
        WHERE LOWER(Approver) = LOWER(@UserCode);
    END

    -- 2. Truy vấn chính
    SELECT 
        T1.QuotationID, T1.QuotationNo, T1.QuotationDate, 
        T1.SaleAmount, T1.SalesManID, T1.EmployeeID,
        T1.VoucherTypeID, T1.ObjectID AS ClientID, 
        ISNULL(T2.ShortObjectName, 'N/A') AS ClientName,
        ISNULL(T2.O05ID, 'N/A') AS CustomerClass, 
        ISNULL(T6.SHORTNAME, 'N/A') AS SalesAdminName,
        ISNULL(T7.SHORTNAME, 'N/A') AS NVKDName,
        
        -- Tính tổng chi tiết (Giữ nguyên logic cũ)
        SUM(T4.ConvertedAmount) AS TotalSaleAmount, 
        SUM(T4.QuoQuantity * COALESCE(T8.Cost, T5.Recievedprice, 0)) AS TotalCost,
        
        -- Logic kiểm tra Cost Override (Giữ nguyên)
        MIN(CASE WHEN (T5.SalePrice01 IS NULL OR T5.SalePrice01 <= 1) OR (T5.Recievedprice IS NULL OR T5.Recievedprice <= 2) THEN 1 ELSE 0 END) AS NeedsCostOverride,
        MAX(CASE WHEN T8.Cost IS NOT NULL AND T8.Cost > 0 THEN 1 ELSE 0 END) AS HasCostOverrideData,

        -- Lấy danh sách người duyệt (String Aggregation)
        (
            SELECT STUFF((
                SELECT ', ' + RTRIM(Approver)
                FROM [OT0006] A
                WHERE A.VoucherTypeID = T1.VoucherTypeID
                FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '')
        ) AS ApproverList

    FROM [OMEGA_STDD].[dbo].[OT2101] AS T1
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T2 ON T1.ObjectID = T2.ObjectID    
    LEFT JOIN [OMEGA_STDD].[dbo].[OT2102] AS T4 ON T1.QuotationID = T4.QuotationID 
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1302] AS T5 ON T4.InventoryID = T5.InventoryID        
    LEFT JOIN [dbo].[GD - NGUOI DUNG] AS T6 ON T1.EmployeeID = T6.USERCODE
    LEFT JOIN [dbo].[GD - NGUOI DUNG] AS T7 ON T1.SalesManID = T7.USERCODE 
    LEFT JOIN [dbo].[BOSUNG_CHAOGIA] AS T8 ON T4.TransactionID = T8.TransactionID

    WHERE 
        -- Bộ lọc cơ bản
        T1.OrderStatus = 0 -- [LƯU Ý] Cập nhật status theo Python logic (1=Mới, 2=Chờ duyệt). Nếu DB dùng 0 thì sửa lại thành 0.
        AND T1.QuotationDate BETWEEN @DateFrom AND @DateTo
        
        AND (
            -- LOGIC PHÂN QUYỀN MỚI (AND)
            
            -- Trường hợp 1: Là Admin -> Xem hết
            (@IsAdmin = 1)
            
            OR 
            
            -- Trường hợp 2: User thường -> Phải thỏa mãn CẢ HAI điều kiện
            (
                -- Điều kiện A: Phải là người tạo phiếu (Chính chủ)
                T1.EmployeeID = @UserCode
                
                AND
                
                -- Điều kiện B: Loại phiếu này nằm trong danh sách User được quyền duyệt
                T1.VoucherTypeID IN (SELECT VoucherTypeID FROM @UserPermissions)
            )
        )

    GROUP BY 
        T1.QuotationID, T1.QuotationNo, T1.QuotationDate, T1.SaleAmount, T1.SalesManID, 
        T1.VoucherTypeID, T1.ObjectID, T1.EmployeeID, 
        ISNULL(T2.ShortObjectName, 'N/A'), ISNULL(T2.O05ID, 'N/A'), 
        ISNULL(T6.SHORTNAME, 'N/A'), ISNULL(T7.SHORTNAME, 'N/A')
    
    ORDER BY T1.QuotationDate DESC; -- Nên sort DESC để thấy phiếu mới nhất trước
END