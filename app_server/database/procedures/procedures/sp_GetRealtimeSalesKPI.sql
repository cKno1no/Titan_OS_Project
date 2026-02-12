
CREATE PROCEDURE [dbo].[sp_GetRealtimeSalesKPI]
    @SalesmanID NVARCHAR(10) = NULL,
    @CurrentYear INT
AS
BEGIN
    SET NOCOUNT ON;
    SET ANSI_PADDING OFF; 

    -- 1. KHAI BÁO BIẾN THỜI GIAN
    DECLARE @Today DATE = GETDATE();
    
    -- THÊM BIẾN GIỚI HẠN 270 NGÀY (9 THÁNG)
    DECLARE @OrderDateLimit DATE = DATEADD(day, -270, @Today);

    DECLARE @StartOfWeek DATE = DATEADD(wk, DATEDIFF(wk, 0, @Today), 0);
    DECLARE @EndOfWeek DATE = DATEADD(wk, DATEDIFF(wk, 0, @Today), 6);
    DECLARE @StartOfMonth DATE = DATEADD(month, DATEDIFF(month, 0, @Today), 0);
    DECLARE @EndOfMonth DATE = DATEADD(month, DATEDIFF(month, 0, @Today) + 1, -1);
    
    DECLARE @StartOfLastYear DATE = DATEFROMPARTS(@CurrentYear - 1, 1, 1);
    DECLARE @EndOfLastYear DATE = DATEFROMPARTS(@CurrentYear - 1, 12, 31);
    
    -- Khoảng thời gian 3 tháng tới cho mục Sắp giao
    DECLARE @NextThreeMonthsStart DATE = DATEADD(month, DATEDIFF(month, 0, @Today) + 1, 0);
    DECLARE @NextThreeMonthsEnd DATE = DATEADD(day, -1, DATEADD(month, 4, @StartOfMonth));
    
    
    -- =========================================================================
    -- 1. KPI TỔNG HỢP (DOANH SỐ & TỔNG GIÁ TRỊ CHỜ GIAO)
    -- [UPDATE]: Áp dụng lọc OrderDate >= @OrderDateLimit cho phần PO
    -- =========================================================================
    WITH PendingOrderAmount AS (
        SELECT 
            SUM( (T2.OrderQuantity - ISNULL(Delivered.Qty, 0)) * T2.SalePrice ) AS TotalPOA
        FROM [OMEGA_STDD].[dbo].[OT2001] AS T1
        INNER JOIN [OMEGA_STDD].[dbo].[OT2002] AS T2 ON T1.SOrderID = T2.SOrderID
        
        OUTER APPLY (
            SELECT SUM(W.ActualQuantity) AS Qty
            FROM [OMEGA_STDD].[dbo].[WT2007] W
            INNER JOIN [OMEGA_STDD].[dbo].[WT2006] H ON W.VoucherID = H.VoucherID
            WHERE W.OTransactionID = T2.TransactionID 
              AND H.VoucherTypeID = 'PX'
              AND W.DebitAccountID LIKE '632%' 
              AND W.CreditAccountID LIKE '156%'
        ) AS Delivered

        WHERE 
            T1.orderStatus = 1 
            AND T1.orderDate >= @OrderDateLimit -- <--- LỌC 270 NGÀY
            AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = RTRIM(@SalesmanID))
            AND (T2.OrderQuantity - ISNULL(Delivered.Qty, 0)) > 0
    ),
    FilteredSales AS (
        SELECT 
            T1.ConvertedAmount, T1.TranYear, T1.VoucherDate
        FROM [OMEGA_STDD].dbo.GT9000 AS T1 
        WHERE T1.DebitAccountID = '13111' AND T1.CreditAccountID LIKE '5%' 
            AND T1.TranYear >= @CurrentYear - 1
            AND (T1.TranYear < @CurrentYear OR T1.VoucherDate <= @Today)
            AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = RTRIM(@SalesmanID))
    )
    SELECT
        'Sales' AS KPI_Type,
        SUM(CASE WHEN T1.VoucherDate BETWEEN @StartOfWeek AND @EndOfWeek THEN ISNULL(T1.ConvertedAmount, 0) ELSE 0 END) AS Sales_CurrentWeek,
        SUM(CASE WHEN T1.VoucherDate BETWEEN @StartOfMonth AND @EndOfMonth THEN ISNULL(T1.ConvertedAmount, 0) ELSE 0 END) AS Sales_CurrentMonth,
        SUM(CASE WHEN T1.TranYear = @CurrentYear THEN ISNULL(T1.ConvertedAmount, 0) ELSE 0 END) AS Sales_YTD,
        SUM(CASE WHEN T1.VoucherDate BETWEEN @StartOfLastYear AND @EndOfLastYear THEN ISNULL(T1.ConvertedAmount, 0) ELSE 0 END) AS Sales_LastYear,
        
        ISNULL((SELECT TotalPOA FROM PendingOrderAmount), 0) AS PendingOrdersAmount 
    FROM FilteredSales AS T1
    HAVING COUNT(*) > 0 OR @SalesmanID IS NULL;


    -- =========================================================================
    -- 2. TOP 20 ĐƠN HÀNG CHỜ GIAO LỚN NHẤT (PO Tồn)
    -- [UPDATE]: Áp dụng lọc OrderDate >= @OrderDateLimit
    -- =========================================================================
    SELECT TOP 20 
        T1.VoucherNo, 
        CONVERT(VARCHAR(10), T1.orderDate, 120) AS TranDate, 
        T1.ObjectID, 
        T3.ShortObjectName AS ClientName, 
        SUM( (T2.OrderQuantity - ISNULL(Delivered.Qty, 0)) * T2.SalePrice ) AS TotalConvertedAmount

    FROM [OMEGA_STDD].[dbo].[OT2001] AS T1
    INNER JOIN [OMEGA_STDD].[dbo].[OT2002] AS T2 ON T1.SOrderID = T2.SOrderID
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T3 ON T1.ObjectID = T3.ObjectID
    
    OUTER APPLY (
        SELECT SUM(W.ActualQuantity) AS Qty
        FROM [OMEGA_STDD].[dbo].[WT2007] W
        INNER JOIN [OMEGA_STDD].[dbo].[WT2006] H ON W.VoucherID = H.VoucherID
        WHERE W.OTransactionID = T2.TransactionID 
          AND H.VoucherTypeID = 'PX'
          AND W.DebitAccountID LIKE '632%' AND W.CreditAccountID LIKE '156%'
    ) AS Delivered

    WHERE T1.orderStatus = 1 
      AND T1.orderDate >= @OrderDateLimit -- <--- LỌC 270 NGÀY
      AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = RTRIM(@SalesmanID))
      
    GROUP BY T1.VoucherNo, T1.orderDate, T1.ObjectID, T3.ShortObjectName
    
    HAVING SUM( (T2.OrderQuantity - ISNULL(Delivered.Qty, 0)) * T2.SalePrice ) > 0
    
    ORDER BY TotalConvertedAmount DESC;


    -- =========================================================================
    -- 3. TOP 10 ĐƠN HÀNG LỚN NHẤT THÁNG
    -- (Không cần lọc 270 ngày vì đã lọc trong tháng hiện tại)
    -- =========================================================================
    SELECT TOP 10 
        T1.VoucherNo, 
        T2.ShortObjectName AS ClientName, 
        T1.saleAmount AS TotalConvertedAmount
    FROM [OMEGA_STDD].[dbo].[OT2001] AS T1 
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T2 ON T1.ObjectID = T2.ObjectID 
    WHERE T1.orderDate BETWEEN @StartOfMonth AND @EndOfMonth AND T1.orderStatus = 1
        AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = RTRIM(@SalesmanID))
    ORDER BY T1.SALEAmount DESC;


    -- =========================================================================
    -- 4. TOP 10 BÁO GIÁ LỚN NHẤT THÁNG
    -- (Giữ nguyên)
    -- =========================================================================
    IF EXISTS (
        SELECT 1 FROM [OMEGA_STDD].[dbo].[OT2101] AS T1 
        WHERE T1.QuotationDate BETWEEN @StartOfMonth AND @EndOfMonth AND T1.OrderStatus = 1 
        AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = RTRIM(@SalesmanID))
    )
    BEGIN
        SELECT TOP 10
            T1.QuotationNo AS VoucherNo, 
            CONVERT(VARCHAR(10), T1.QuotationDate, 120) AS QuoteDate,
            T1.SaleAmount AS QuoteAmount, 
            T2.ShortObjectName AS ClientName 
        FROM [OMEGA_STDD].[dbo].[OT2101] AS T1 
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T2 ON T1.ObjectID = T2.ObjectID 
        WHERE T1.QuotationDate BETWEEN @StartOfMonth AND @EndOfMonth AND T1.OrderStatus = 1 
            AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = RTRIM(@SalesmanID))
        ORDER BY T1.SaleAmount DESC;
    END
    ELSE
    BEGIN
        SELECT TOP 0 CAST(NULL AS NVARCHAR(10)) AS VoucherNo, CAST(NULL AS DATE) AS QuoteDate, 0.0 AS QuoteAmount, CAST(NULL AS NVARCHAR(100)) AS ClientName FROM [OMEGA_STDD].dbo.GT9000 WHERE 1=0; 
    END


    -- =========================================================================
    -- 5. HÀNG SẮP GIAO (3 THÁNG TỚI)
    -- [UPDATE]: Áp dụng lọc OrderDate >= @OrderDateLimit
    -- =========================================================================
    
    IF EXISTS (
        SELECT 1 FROM [OMEGA_STDD].[dbo].[OT2002] AS T1 
        INNER JOIN [OMEGA_STDD].[dbo].[OT2001] AS T2 ON T1.SOrderID = T2.SOrderID
        WHERE T2.orderStatus = 1 
          AND T1.Date01 BETWEEN @NextThreeMonthsStart AND @NextThreeMonthsEnd
          AND T2.orderDate >= @OrderDateLimit -- <--- LỌC 270 NGÀY (Kiểm tra chéo)
          AND (@SalesmanID IS NULL OR RTRIM(T2.SalesManID) = RTRIM(@SalesmanID))
    )
    BEGIN
        SELECT TOP 20
            T2.VoucherNo, 
            T2.ObjectID, 
            T3.ShortObjectName AS ClientName, 
            T1.InventoryID, 
            T4.InventoryName, 
            CONVERT(VARCHAR(10), T1.Date01, 120) AS DeliverDate, 
            (T1.OrderQuantity - ISNULL(Delivered.Qty, 0)) AS RemainingQuantity, 
            T1.SalePrice * (T1.OrderQuantity - ISNULL(Delivered.Qty, 0)) AS RemainingValue 

        FROM [OMEGA_STDD].[dbo].[OT2002] AS T1 
        INNER JOIN [OMEGA_STDD].[dbo].[OT2001] AS T2 ON T1.SOrderID = T2.SOrderID
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T3 ON T2.ObjectID = T3.ObjectID
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1302] AS T4 ON T1.InventoryID = T4.InventoryID
        
        OUTER APPLY (
            SELECT SUM(W.ActualQuantity) AS Qty
            FROM [OMEGA_STDD].[dbo].[WT2007] W
            INNER JOIN [OMEGA_STDD].[dbo].[WT2006] H ON W.VoucherID = H.VoucherID
            WHERE W.OTransactionID = T1.TransactionID 
              AND H.VoucherTypeID = 'PX'            
              AND W.DebitAccountID LIKE '632%'       
              AND W.CreditAccountID LIKE '156%'      
        ) AS Delivered

        WHERE T2.orderStatus = 1 
            AND T1.Date01 BETWEEN @NextThreeMonthsStart AND @NextThreeMonthsEnd
            AND T2.orderDate >= @OrderDateLimit -- <--- LỌC 270 NGÀY
            AND (@SalesmanID IS NULL OR RTRIM(T2.SalesManID) = RTRIM(@SalesmanID))
            AND (T1.OrderQuantity - ISNULL(Delivered.Qty, 0)) > 0

        ORDER BY RemainingValue DESC; 
    END
    ELSE
    BEGIN
        SELECT TOP 0 
            CAST(NULL AS NVARCHAR(10)) AS VoucherNo, CAST(NULL AS NVARCHAR(10)) AS ObjectID, CAST(NULL AS NVARCHAR(100)) AS ClientName, 
            CAST(NULL AS NVARCHAR(10)) AS InventoryID, CAST(NULL AS NVARCHAR(100)) AS InventoryName, CAST(NULL AS DATE) AS DeliverDate, 
            0 AS RemainingQuantity, 0.0 AS RemainingValue
        FROM [OMEGA_STDD].dbo.GT9000 WHERE 1 = 0; 
    END

END