CREATE PROCEDURE [dbo].[sp_GetSalesGrossProfit_Analysis_HN]
    @FromDate DATE,
    @ToDate DATE,
    @SalesmanID NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- ========================================================================
    -- BƯỚC 1: TÍNH GIÁ VỐN - Gom nhóm theo SalesOrderID và InventoryID
    -- Thay vì theo OTransactionID (dễ bị lệch giữa Hóa đơn và Phiếu xuất),
    -- ta gom theo Mã hàng trong Đơn hàng (SOrderID + InventoryID)
    -- ========================================================================
    WITH ActualCOGS AS (
        SELECT 
            D.SOrderID,          -- ID Đơn hàng
            D.InventoryID,       -- Mã hàng
            SUM(W.ConvertedAmount) AS TotalCostValue,
            SUM(W.ActualQuantity) AS TotalQtyOut
        FROM [OMEGA_TEST].[dbo].[WT2007] AS W
        INNER JOIN [OMEGA_TEST].[dbo].[WT2006] AS H ON W.VoucherID = H.VoucherID
        -- Join về OT2002 để lấy SOrderID chuẩn xác
        LEFT JOIN [OMEGA_TEST].[dbo].[OT2002] AS D ON W.OTransactionID = D.TransactionID
        WHERE 
            H.VoucherTypeID IN ('PPX', 'PXK') -- Thêm PXK đề phòng chi nhánh HN dùng mã khác
            AND W.DebitAccountID LIKE '632%'  -- Chỉ lấy dòng hạch toán 632
            AND H.VoucherDate >= DATEADD(MONTH, -1, @FromDate) 
            AND H.VoucherDate <= DATEADD(MONTH, 1, @ToDate)
            AND D.SOrderID IS NOT NULL -- Chỉ lấy dòng có liên kết đơn hàng
        GROUP BY D.SOrderID, D.InventoryID
    )

    -- ========================================================================
    -- BƯỚC 2: TRUY VẤN CHÍNH
    -- ========================================================================
    SELECT 
        GL.VoucherDate AS NgayHachToan,
        GL.VoucherNo AS SoChungTu,
        ORD.VoucherNo AS SoDonHang,
        ISNULL(ORD.SalesManID, GL.SalesManID) AS SalesManID, 
        USERS.SHORTNAME AS SalesManName,
        GL.ObjectID AS MaKhachHang,
        CUST.ShortObjectName AS TenKhachHang,
        GL.InventoryID AS MaHang,
        ITEM.InventoryName AS TenHang,
        ITEM.UnitID AS DVT,
        ITEM.I02ID AS NhomHang,
        
        -- Số liệu
        GL.Quantity AS SoLuong,
        GL.ConvertedAmount AS DoanhThu,

        -- GIÁ VỐN (Join theo SOrderID và InventoryID)
        CAST(
            CASE 
                WHEN ISNULL(COST.TotalQtyOut, 0) > 0 
                THEN (COST.TotalCostValue / COST.TotalQtyOut) * GL.Quantity 
                ELSE 0 
            END 
        AS DECIMAL(18, 0)) AS GiaVon,

        -- LÃI GỘP
        CAST(
            (GL.ConvertedAmount - 
                CASE 
                    WHEN ISNULL(COST.TotalQtyOut, 0) > 0 
                    THEN (COST.TotalCostValue / COST.TotalQtyOut) * GL.Quantity 
                    ELSE 0 
                END
            ) 
        AS DECIMAL(18, 0)) AS LaiGop,

        -- % MARGIN
        CAST(
            CASE 
                WHEN GL.ConvertedAmount <> 0 
                THEN ((GL.ConvertedAmount - 
                        CASE 
                            WHEN ISNULL(COST.TotalQtyOut, 0) > 0 
                            THEN (COST.TotalCostValue / COST.TotalQtyOut) * GL.Quantity 
                            ELSE 0 
                        END
                      ) / GL.ConvertedAmount) * 100
                ELSE 0 
            END 
        AS DECIMAL(10, 2)) AS TyLeLaiGop

    FROM [OMEGA_TEST].[dbo].[GT9000] AS GL
    
    -- JOIN ĐỂ LẤY SORDERID TỪ DOANH THU (QUAN TRỌNG)
    LEFT JOIN [OMEGA_TEST].[dbo].[OT2002] AS ORD_DETAIL ON GL.OTransactionID = ORD_DETAIL.TransactionID
    LEFT JOIN [OMEGA_TEST].[dbo].[OT2001] AS ORD ON ORD_DETAIL.SOrderID = ORD.SOrderID

    -- JOIN VỚI CTE GIÁ VỐN (KHỚP THEO SORDERID + INVENTORYID)
    LEFT JOIN ActualCOGS AS COST ON ORD.SOrderID = COST.SOrderID AND GL.InventoryID = COST.InventoryID
    
    -- CÁC JOIN KHÁC
    LEFT JOIN [OMEGA_TEST].[dbo].[IT1202] AS CUST ON GL.ObjectID = CUST.ObjectID
    LEFT JOIN [OMEGA_TEST].[dbo].[IT1302] AS ITEM ON GL.InventoryID = ITEM.InventoryID
    LEFT JOIN [CRM_STDD].[dbo].[GD - NGUOI DUNG] AS USERS ON ISNULL(ORD.SalesManID, GL.SalesManID) = USERS.USERCODE

    WHERE 
        GL.CreditAccountID LIKE '511%' 
        AND GL.VoucherDate BETWEEN @FromDate AND @ToDate
        AND (@SalesmanID IS NULL OR ISNULL(ORD.SalesManID, GL.SalesManID) = @SalesmanID)

    ORDER BY GL.VoucherDate DESC, GL.VoucherNo;
END;