
CREATE PROCEDURE dbo.sp_GetSalesLookup_Block1
    @ItemSearchTerm NVARCHAR(MAX), -- Bây giờ sẽ là: '23152, 6220'
    @ObjectID NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ThreeYearsAgo DATE = DATEADD(year, -3, GETDATE());
    DECLARE @TwoYearsAgo DATE = DATEADD(year, -2, GETDATE());
    DECLARE @Today DATE = GETDATE();

    IF @ObjectID = '' SET @ObjectID = NULL;

    -- 1. Tách chuỗi tìm kiếm
    SELECT RTRIM(LTRIM(SplitData)) AS SearchTerm
    INTO #SearchTerms
    FROM dbo.fn_SplitString(@ItemSearchTerm, ',')
    WHERE RTRIM(LTRIM(SplitData)) <> '';

    -- 2. Lấy danh sách mặt hàng khớp
    SELECT T1.InventoryID, T1.InventoryName, T1.SalePrice01
    INTO #MatchingItems
    FROM [OMEGA_STDD].[dbo].[IT1302] AS T1
    WHERE EXISTS (
        SELECT 1 FROM #SearchTerms T_S
        WHERE T1.InventoryID LIKE '%' + T_S.SearchTerm + '%' 
           OR T1.InventoryName LIKE '%' + T_S.SearchTerm + '%'
    );
    
    -- Result Set 1: Tồn kho & Giá
    SELECT 
        T1.InventoryID, T1.InventoryName, 
        ISNULL(T2_Sum.Ton, 0) AS Ton, 
        ISNULL(T2_Sum.BackOrder, 0) AS BackOrder,
        T1.SalePrice01 AS GiaBanQuyDinh
    INTO #Block1_Base
    FROM #MatchingItems AS T1
    LEFT JOIN (
        SELECT 
            InventoryID, SUM(Ton) as Ton, SUM(con) as BackOrder 
        FROM [OMEGA_STDD].[dbo].[CRM_TON KHO BACK ORDER]
        GROUP BY InventoryID
    ) AS T2_Sum ON T1.InventoryID = T2_Sum.InventoryID;

    -- Giá bán gần nhất (Hóa đơn)
    SELECT T.InventoryID, T.SalePrice, T.InvoiceDate
    INTO #RecentSale
    FROM (
        SELECT 
            T1.InventoryID, T1.SalePrice, T1.InvoiceDate,
            ROW_NUMBER() OVER(PARTITION BY T1.InventoryID ORDER BY T1.InvoiceDate DESC) as rn
        FROM [OMEGA_STDD].[dbo].[CRM_TV_THONG TIN DHB_FULL] AS T1
        INNER JOIN #MatchingItems T_Filter ON T1.InventoryID = T_Filter.InventoryID
        WHERE T1.InvoiceNo IS NOT NULL
          AND (@ObjectID IS NULL OR T1.ObjectID = @ObjectID)
    ) AS T
    WHERE T.rn = 1;

    -- Giá chào gần nhất (Báo giá)
    SELECT T.InventoryID, T.UnitPrice, T.QuotationDate
    INTO #RecentQuote
    FROM (
        SELECT 
            T1.InventoryID, T1.UnitPrice, T2.QuotationDate,
            ROW_NUMBER() OVER(PARTITION BY T1.InventoryID ORDER BY T2.QuotationDate DESC) as rn
        FROM [OMEGA_STDD].[dbo].[OT2102] AS T1
        JOIN [OMEGA_STDD].[dbo].[OT2101] AS T2 ON T1.QuotationID = T2.QuotationID
        INNER JOIN #MatchingItems T_Filter ON T1.InventoryID = T_Filter.InventoryID
        WHERE 
            T2.QuotationDate BETWEEN @TwoYearsAgo AND @Today
            AND (@ObjectID IS NULL OR T2.ObjectID = @ObjectID)
    ) AS T
    WHERE T.rn = 1;

    -- Trả về Result Set 1
    SELECT 
        T_Base.InventoryID, T_Base.InventoryName, 
        T_Base.Ton, T_Base.BackOrder, 
        ISNULL(T_Base.GiaBanQuyDinh, 0) AS GiaBanQuyDinh,
        ISNULL(T_Sale.SalePrice, 0) AS GiaBanGanNhat_HD,
        ISNULL(T_Quote.UnitPrice, 0) AS GiaChaoGanNhat_BG,
        -- (FIX YÊU CẦU 6) THÊM 2 CỘT NGÀY
        T_Sale.InvoiceDate AS NgayGanNhat_HD,
        T_Quote.QuotationDate AS NgayGanNhat_BG
    FROM #Block1_Base AS T_Base
    LEFT JOIN #RecentSale AS T_Sale ON T_Base.InventoryID = T_Sale.InventoryID
    LEFT JOIN #RecentQuote AS T_Quote ON T_Base.InventoryID = T_Quote.InventoryID
    ORDER BY T_Base.InventoryID;

    -- Result Set 2: Lịch sử ĐHB, PXK, Hóa đơn
    SELECT TOP 20
        VoucherNo, OrderDate, 
        InventoryID, InventoryName, OrderQuantity, SalePrice,
        Description AS SoPXK, VoucherDate AS NgayPXK, ActualQuantity AS SL_PXK, 
        InvoiceNo AS SoHoaDon, InvoiceDate AS NgayHoaDon, Quantity AS SL_HoaDon
    FROM [OMEGA_STDD].[dbo].[CRM_TV_THONG TIN DHB_FULL]
    WHERE 
        (@ObjectID IS NULL OR ObjectID = @ObjectID) 
        AND EXISTS (
            SELECT 1 FROM #MatchingItems T_Filter 
            WHERE [CRM_TV_THONG TIN DHB_FULL].InventoryID = T_Filter.InventoryID
        )
    ORDER BY OrderDate DESC;

    -- Result Set 3: Lịch sử PO, Phiếu nhập kho (Không lọc KH)
    SELECT TOP 20
        VoucherNo, OrderDate, 
        InventoryID, InventoryName, OrderQuantity, SalePrice,
        PO AS SoPO, ShipDate AS NgayPO, [PO SL] AS SL_PO, 
        Description AS SoPN, VoucherDate AS NgayPN, ActualQuantity AS SL_PN
    FROM [OMEGA_STDD].[dbo].[CRM_TV_THONG TIN DHB_FULL 2]
    WHERE 
        EXISTS ( 
            SELECT 1 FROM #MatchingItems T_Filter 
            WHERE [CRM_TV_THONG TIN DHB_FULL 2].InventoryID = T_Filter.InventoryID
        )
    ORDER BY OrderDate DESC;

    -- Dọn dẹp
    DROP TABLE #SearchTerms;
    DROP TABLE #MatchingItems;
    DROP TABLE #Block1_Base;
    DROP TABLE #RecentSale;
    DROP TABLE #RecentQuote;
END
