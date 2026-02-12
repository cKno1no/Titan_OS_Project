
CREATE PROCEDURE dbo.sp_GetSalesLookup_Common
    @InventoryIDs NVARCHAR(MAX), 
    @ObjectID NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ThreeYearsAgo DATE = DATEADD(year, -3, GETDATE());
    DECLARE @TwoYearsAgo DATE = DATEADD(year, -2, GETDATE());
    DECLARE @Today DATE = GETDATE();

    -- 1. Tách chuỗi (Dùng hàm của CRM_STDD)
    SELECT RTRIM(LTRIM(SplitData)) AS InventoryID
    INTO #InvIDs
    FROM dbo.fn_SplitString(@InventoryIDs, ',')
    WHERE RTRIM(LTRIM(SplitData)) <> '';
    
    IF @ObjectID = '' SET @ObjectID = NULL;

    -- Result Set 1: Tồn kho (Truy vấn liên CSDL)
    SELECT 
        T1.InventoryID, T1.InventoryName, 
        ISNULL(T2.Ton, 0) AS Ton, 
        ISNULL(T2.con, 0) AS BackOrder,
        ISNULL(T1.SalePrice01, 0) AS SalePrice01
    FROM [OMEGA_STDD].[dbo].[IT1302] AS T1
    INNER JOIN #InvIDs T_Filter ON T1.InventoryID = T_Filter.InventoryID
    LEFT JOIN [OMEGA_STDD].[dbo].[CRM_TON KHO BACK ORDER] AS T2
        ON T1.InventoryID = T2.InventoryID;
        

    -- Result Set 2: Giá bán gần nhất (Truy vấn liên CSDL)
    WITH RankedSales AS (
        SELECT 
            T1.InventoryID, T1.UnitPrice AS SalePrice, T1.VoucherDate,
            ROW_NUMBER() OVER(PARTITION BY T1.InventoryID ORDER BY T1.VoucherDate DESC) AS rn
        FROM [OMEGA_STDD].[dbo].[GT9000] AS T1
        INNER JOIN #InvIDs T_Filter ON T1.InventoryID = T_Filter.InventoryID
        WHERE 
            T1.VoucherDate BETWEEN @ThreeYearsAgo AND @Today
            AND T1.CreditAccountID LIKE '5%' 
            AND T1.DebitAccountID LIKE '131%'
            AND (@ObjectID IS NULL OR T1.ObjectID = @ObjectID) 
    )
    SELECT InventoryID, SalePrice, VoucherDate 
    FROM RankedSales 
    WHERE rn = 1;


    -- Result Set 3: Giá chào gần nhất (Truy vấn liên CSDL)
    WITH RankedQuotes AS (
        SELECT 
            T1.InventoryID, T1.UnitPrice AS QuotePrice, T2.QuotationDate,
            ROW_NUMBER() OVER(PARTITION BY T1.InventoryID ORDER BY T2.QuotationDate DESC) AS rn
        FROM [OMEGA_STDD].[dbo].[OT2102] AS T1
        INNER JOIN [OMEGA_STDD].[dbo].[OT2101] AS T2 ON T1.QuotationID = T2.QuotationID
        INNER JOIN #InvIDs T_Filter ON T1.InventoryID = T_Filter.InventoryID
        WHERE 
            T2.QuotationDate BETWEEN @TwoYearsAgo AND @Today
            AND (@ObjectID IS NULL OR T2.ObjectID = @ObjectID) 
    )
    SELECT InventoryID, QuotePrice, QuotationDate 
    FROM RankedQuotes 
    WHERE rn = 1;
    
    DROP TABLE #InvIDs;
END
