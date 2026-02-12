
CREATE PROCEDURE [dbo].[sp_GetSalesPerformanceSummary]
    @CurrentYear INT,
    @UserCode NVARCHAR(50) = NULL,
    @IsAdmin BIT = 0,
    @Division NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Khai báo biến thời gian
    DECLARE @StartOfMonth DATE = DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0);
    DECLARE @EndOfMonth DATE = DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, -1);
    
    -- Giới hạn đơn hàng tồn (9 tháng)
    DECLARE @OrderDateLimit DATE = DATEADD(day, -270, GETDATE());

    -- 1. DOANH SỐ YTD & THÁNG (GT9000 - Giữ nguyên)
    SELECT 
        RTRIM(T1.SalesManID) AS SalesManID,
        SUM(T1.ConvertedAmount) AS TotalSalesAmount,
        SUM(CASE WHEN T1.VoucherDate BETWEEN @StartOfMonth AND @EndOfMonth THEN T1.ConvertedAmount ELSE 0 END) AS CurrentMonthSales,
        COUNT(DISTINCT T1.VoucherNo) AS TotalOrders
    INTO #SalesSummary
    FROM [OMEGA_STDD].[dbo].[GT9000] AS T1
    WHERE 
        T1.DebitAccountID = '13111' 
        AND T1.CreditAccountID LIKE '5%'
        AND T1.TranYear = @CurrentYear
        AND T1.SalesManID IS NOT NULL
    GROUP BY RTRIM(T1.SalesManID);

    -- 2. DOANH SỐ ĐĂNG KÝ (DTCL - Giữ nguyên)
    SELECT 
        RTRIM([PHU TRACH DS]) AS SalesManID,
        SUM(ISNULL(DK, 0)) AS RegisteredSales
    INTO #RegisteredSummary
    FROM [CRM_STDD].[dbo].[DTCL]
    WHERE [Nam] = @CurrentYear
    GROUP BY RTRIM([PHU TRACH DS]);

    -- 3. [FIX] TÍNH PO TỒN (PENDING) - LOGIC MỚI ĐỒNG BỘ SALES BACKLOG
    -- Logic: Lấy các đơn hàng Status = 1 (Chưa hoàn tất), chưa hủy, trong 9 tháng
    SELECT 
        RTRIM(H.SalesManID) AS SalesManID,
        SUM(D.ConvertedAmount - (ISNULL(Shipped.Qty, 0) * D.SalePrice)) AS PendingOrdersAmount
    INTO #PendingSummary
    FROM [OMEGA_STDD].[dbo].[OT2001] H
    INNER JOIN [OMEGA_STDD].[dbo].[OT2002] D ON H.SOrderID = D.SOrderID
    
    -- Tính số lượng đã giao (Xử lý mã bộ)
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

    WHERE 
        H.OrderStatus = 1 -- Chưa hoàn tất
        AND H.VoucherTypeID <> 'DTK'
        AND H.OrderDate >= @OrderDateLimit -- Trong vòng 9 tháng
        AND (D.OrderQuantity - ISNULL(Shipped.Qty, 0)) > 0 -- Còn hàng chưa giao
    GROUP BY RTRIM(H.SalesManID);

    -- 4. TỔNG HỢP KẾT QUẢ
    SELECT 
        COALESCE(S.SalesManID, R.SalesManID, P.SalesManID) AS EmployeeID,
        ISNULL(U.SHORTNAME, COALESCE(S.SalesManID, R.SalesManID, P.SalesManID)) AS SalesManName,
        ISNULL(S.TotalSalesAmount, 0) AS TotalSalesAmount,
        ISNULL(S.CurrentMonthSales, 0) AS CurrentMonthSales,
        ISNULL(S.TotalOrders, 0) AS TotalOrders,
        ISNULL(R.RegisteredSales, 0) AS RegisteredSales,
        ISNULL(P.PendingOrdersAmount, 0) AS PendingOrdersAmount
    FROM #SalesSummary S
    FULL OUTER JOIN #RegisteredSummary R ON S.SalesManID = R.SalesManID
    FULL OUTER JOIN #PendingSummary P ON ISNULL(S.SalesManID, R.SalesManID) = P.SalesManID
    LEFT JOIN [CRM_STDD].[dbo].[GD - NGUOI DUNG] U ON ISNULL(S.SalesManID, ISNULL(R.SalesManID, P.SalesManID)) = U.USERCODE
    WHERE 
        (@IsAdmin = 1 OR COALESCE(S.SalesManID, R.SalesManID, P.SalesManID) = @UserCode)
        AND COALESCE(S.SalesManID, R.SalesManID, P.SalesManID) IS NOT NULL
        AND (@Division IS NULL OR U.[Division] = @Division);

    DROP TABLE #SalesSummary;
    DROP TABLE #RegisteredSummary;
    DROP TABLE #PendingSummary;
END;
