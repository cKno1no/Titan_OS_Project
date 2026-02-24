
CREATE PROCEDURE [dbo].[Titan_Get_SalesBacklog]
    @DateFrom DATE,
    @DateTo DATE,
    @SalesManID VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT 
        H.VoucherNo AS OrderID,
        H.OrderDate,
        H.ObjectID AS ClientID,
        C.ShortObjectName AS ClientName,
        
        -- [MỚI] Nhân viên Kinh doanh
        H.SalesManID,
        SM.SHORTNAME AS SalesmanName,

        -- [MỚI] Thư ký Kinh doanh (Người theo dõi - EmployeeID)
        H.EmployeeID AS SalesAdminID,
        TK.SHORTNAME AS SalesAdminName,
        
        D.InventoryID,
        I.InventoryName,
        D.UnitID,
        D.OrderQuantity AS SoLuongDat,
        
        -- Số lượng đã giao (Tính toán từ Logic OUTER APPLY đã fix)
        ISNULL(Shipped.Qty, 0) AS SoLuongDaGiao,

        -- Đơn giá
        D.SalePrice AS DonGia,
        
        -- [A] TỔNG DOANH SỐ CHỜ (Giá trị dòng PO)
        D.ConvertedAmount AS GiaTriDonHang, 
        
        -- [B] ĐÃ GIAO - CHƯA HD
        (ISNULL(Shipped.Qty, 0) * D.SalePrice) AS GiaTriDaGiao_ChuaHD, 
        
        -- [C] CHƯA GIAO HÀNG (Áp dụng công thức đơn giản hóa: C = A - B)
        (D.ConvertedAmount - (ISNULL(Shipped.Qty, 0) * D.SalePrice)) AS GiaTriChuaGiao, 
        
        DATEDIFF(day, H.OrderDate, GETDATE()) AS NgayCho

    FROM [OMEGA_STDD].[dbo].[OT2001] H 
    INNER JOIN [OMEGA_STDD].[dbo].[OT2002] D ON H.SOrderID = D.SOrderID 
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] C ON H.ObjectID = C.ObjectID 
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1302] I ON D.InventoryID = I.InventoryID 
    
    -- Tính toán số lượng đã giao
    OUTER APPLY (
        SELECT SUM(SubCalc.ConvertedQty) AS Qty
        FROM (
            SELECT 
                CASE 
                    WHEN BOM.ItemQuantity > 0 THEN T1.ActualQuantity / BOM.ItemQuantity
                    ELSE T1.ActualQuantity
                END AS ConvertedQty
            FROM [OMEGA_STDD].[dbo].[WT2007] T1
            INNER JOIN [OMEGA_STDD].[dbo].[WT2006] T2 ON T1.VoucherID = T2.VoucherID
            LEFT JOIN [OMEGA_STDD].[dbo].[IT1326] BOM 
                ON BOM.InventoryID = D.InventoryID AND BOM.ItemID = T1.InventoryID
            WHERE T1.OTransactionID = D.TransactionID AND T2.VoucherTypeID = 'VC'
        ) SubCalc
    ) Shipped

    LEFT JOIN [OMEGA_STDD].[dbo].[GT9000] INV ON D.TransactionID = INV.OTransactionID 
    
    -- Join User: Salesman
    LEFT JOIN [dbo].[GD - NGUOI DUNG] SM ON H.SalesManID = SM.USERCODE
    -- Join User: Sales Admin (Thư ký)
    LEFT JOIN [dbo].[GD - NGUOI DUNG] TK ON H.EmployeeID = TK.USERCODE

    WHERE 
        H.VoucherTypeID <> 'DTK' 
        AND H.OrderStatus IN (0, 1, 2) 
        AND INV.OTransactionID IS NULL 
        AND H.OrderDate BETWEEN @DateFrom AND @DateTo
        AND (@SalesManID IS NULL OR H.SalesManID = @SalesManID)

    ORDER BY H.OrderDate ASC;
END

GO
