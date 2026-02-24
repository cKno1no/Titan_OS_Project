
CREATE PROCEDURE [dbo].[sp_GetSalesPerformanceSummary_HN]
    @CurrentYear INT,
    @UserCode NVARCHAR(50) = NULL,
    @IsAdmin BIT = 0,
    @Division NVARCHAR(50) = NULL -- [MỚI] Thêm tham số Division
AS
BEGIN
    SET NOCOUNT ON;

    -- Khai báo các biến thời gian
    DECLARE @StartOfYear DATE = DATEFROMPARTS(@CurrentYear, 1, 1);
    DECLARE @EndOfYear DATE = DATEFROMPARTS(@CurrentYear, 12, 31);
    DECLARE @StartOfMonth DATE = DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0);
    DECLARE @EndOfMonth DATE = DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, -1);
    
    -- Giới hạn đơn hàng tồn (9 tháng)
    DECLARE @OrderDateLimit DATE = DATEADD(day, -270, GETDATE());

    -- 1. Tính Doanh số YTD và Tháng hiện tại (Nguồn: GT9000)
    SELECT 
        RTRIM(T1.SalesManID) AS SalesManID,
        SUM(T1.ConvertedAmount) AS TotalSalesAmount, -- YTD
        SUM(CASE WHEN T1.VoucherDate BETWEEN @StartOfMonth AND @EndOfMonth THEN T1.ConvertedAmount ELSE 0 END) AS CurrentMonthSales,
        COUNT(DISTINCT T1.VoucherNo) AS TotalOrders
    INTO #SalesSummary
    FROM [OMEGA_TEST].[dbo].[GT9000] AS T1
    WHERE 
        T1.DebitAccountID = '13111' 
        AND T1.CreditAccountID LIKE '5%'
        AND T1.TranYear = @CurrentYear
        AND T1.SalesManID IS NOT NULL
    GROUP BY RTRIM(T1.SalesManID);

    -- 2. Tính Doanh số Đăng ký (Nguồn: DTCL)
    SELECT 
        RTRIM([PHU TRACH DS]) AS SalesManID,
        SUM(ISNULL(DK, 0)) AS RegisteredSales
    INTO #RegisteredSummary
    FROM [CRM_STDD].[dbo].[DTCL]
    WHERE [Nam] = @CurrentYear
    GROUP BY RTRIM([PHU TRACH DS]);

    -- 3. Tính PO Tồn (Đơn hàng chờ giao) - LOGIC CHUẨN (MỚI)
    SELECT 
        RTRIM(T1.SalesManID) AS SalesManID,
        -- Tổng giá trị còn lại của các dòng hàng chưa giao hết
        SUM( (T2.OrderQuantity - ISNULL(Delivered.Qty, 0)) * T2.SalePrice ) AS PendingOrdersAmount
    INTO #PendingSummary
    FROM [OMEGA_TEST].[dbo].[OT2001] AS T1
    INNER JOIN [OMEGA_TEST].[dbo].[OT2002] AS T2 ON T1.SOrderID = T2.SOrderID
    
    -- Tính số lượng đã xuất kho (PX + Định khoản)
    OUTER APPLY (
        SELECT SUM(W.ActualQuantity) AS Qty
        FROM [OMEGA_TEST].[dbo].[WT2007] W
        INNER JOIN [OMEGA_TEST].[dbo].[WT2006] H ON W.VoucherID = H.VoucherID
        WHERE W.OTransactionID = T2.TransactionID 
          AND H.VoucherTypeID = 'PX'
          AND W.DebitAccountID LIKE '632%' 
          AND W.CreditAccountID LIKE '156%'
    ) AS Delivered

    WHERE 
        T1.orderStatus = 1 
        AND T1.orderDate >= @OrderDateLimit -- Lọc 270 ngày
        -- Chỉ lấy dòng còn nợ hàng
        AND (T2.OrderQuantity - ISNULL(Delivered.Qty, 0)) > 0
    GROUP BY RTRIM(T1.SalesManID);

    -- 4. Tổng hợp tất cả và Trả về kết quả
    -- Logic: Lấy danh sách nhân viên từ bảng User hoặc từ các bảng số liệu
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
        -- Phân quyền: Admin thấy hết, User chỉ thấy mình
        (@IsAdmin = 1 OR COALESCE(S.SalesManID, R.SalesManID, P.SalesManID) = @UserCode)
        -- Loại bỏ các dòng rác không có mã nhân viên
        AND COALESCE(S.SalesManID, R.SalesManID, P.SalesManID) IS NOT NULL
        -- [MỚI QUAN TRỌNG] Lọc theo Division nếu tham số được truyền vào
        AND (@Division IS NULL OR U.[Division] = @Division);

    -- Dọn dẹp
    DROP TABLE #SalesSummary;
    DROP TABLE #RegisteredSummary;
    DROP TABLE #PendingSummary;
END;

GO
