
CREATE PROCEDURE [dbo].[sp_GetInventoryAging_HN]
    @InventoryIDList NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @SQL NVARCHAR(MAX);
    DECLARE @Today DATE = GETDATE();
    DECLARE @CurrentMonth INT = MONTH(@Today);
    DECLARE @CurrentYear INT = YEAR(@Today);
    DECLARE @RiskThreshold DECIMAL(19, 4) = 5000000.0; -- 5 Triệu VNĐ (Rủi ro)

    -- Khai báo Bảng ERP
    DECLARE @IT1301 NVARCHAR(100) = N'[OMEGA_TEST].[dbo].[IT1301]';
    DECLARE @IT1302 NVARCHAR(100) = N'[OMEGA_TEST].[dbo].[IT1302]';
    DECLARE @WT2008 NVARCHAR(100) = N'[OMEGA_TEST].[dbo].[WT2008]'; 
    
    IF LTRIM(RTRIM(ISNULL(@InventoryIDList, ''))) = ''
    BEGIN
        SET @InventoryIDList = NULL;
    END

    -- Xây dựng truy vấn chính
    SET @SQL = N'
    WITH LastReceiptDate AS (
        -- Lấy ngày nhập kho cuối cùng (Max VoucherDate)
        SELECT T2.InventoryID, MAX(T1.VoucherDate) AS MaxReceiptDate
        FROM [OMEGA_TEST].[dbo].[WT2006] AS T1 
        INNER JOIN [OMEGA_TEST].[dbo].[WT2007] AS T2 ON T1.VoucherID = T2.VoucherID
        WHERE T1.VoucherTypeID = ''PPN''
        GROUP BY T2.InventoryID
    )
    SELECT
        T_CUR.InventoryID,
        T_ITEM.InventoryName,
        T_ITEM.I02ID AS ItemCategory, 
        T_TYPE.InventoryTypeName, 
        T_ITEM.I05ID AS StockClass, 
        
        T_CUR.EndAmount AS TotalCurrentValue,
        T_CUR.EndQuantity AS TotalCurrentQuantity,
        
        -- CÁC CỘT PHÂN NHÓM
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) <= 180 THEN T_CUR.EndAmount ELSE 0 END) AS Range_0_180_V,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) BETWEEN 181 AND 360 THEN T_CUR.EndAmount ELSE 0 END) AS Range_181_360_V,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) BETWEEN 361 AND 540 THEN T_CUR.EndAmount ELSE 0 END) AS Range_361_540_V,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) BETWEEN 541 AND 720 THEN T_CUR.EndAmount ELSE 0 END) AS Range_541_720_V,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) > 720 THEN T_CUR.EndAmount ELSE 0 END) AS Range_Over_720_V,

        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) <= 180 THEN T_CUR.EndQuantity ELSE 0 END) AS Range_0_180_Q,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) BETWEEN 181 AND 360 THEN T_CUR.EndQuantity ELSE 0 END) AS Range_181_360_Q,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) BETWEEN 361 AND 540 THEN T_CUR.EndQuantity ELSE 0 END) AS Range_361_540_Q,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) BETWEEN 541 AND 720 THEN T_CUR.EndQuantity ELSE 0 END) AS Range_541_720_Q,
        SUM(CASE WHEN DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) > 720 THEN T_CUR.EndQuantity ELSE 0 END) AS Range_Over_720_Q,
        
        -- YÊU CẦU 2: CỘT D (RỦI RO CLC)
        SUM(CASE 
            WHEN T_ITEM.I05ID != ''D'' AND T_ITEM.I05ID IS NOT NULL AND DATEDIFF(day, T_LAST.MaxReceiptDate, @Today) > 720 AND T_CUR.EndAmount > @RiskThreshold
            THEN T_CUR.EndAmount 
            ELSE 0 
        END) AS Risk_CLC_Value

    FROM ' + @WT2008 + ' AS T_CUR 
    INNER JOIN LastReceiptDate AS T_LAST ON T_CUR.InventoryID = T_LAST.InventoryID
    LEFT JOIN ' + @IT1302 + ' AS T_ITEM ON T_CUR.InventoryID = T_ITEM.InventoryID
    LEFT JOIN ' + @IT1301 + ' AS T_TYPE ON T_ITEM.I02ID = T_TYPE.InventoryTypeID

    WHERE 
        T_CUR.WareHouseID IN (''STDP'', ''TGP19'', ''PM'')
        AND T_CUR.EndQuantity > 0 
        AND T_CUR.TranMonth = @CurrentMonth
        AND T_CUR.TranYear = @CurrentYear
        AND T_ITEM.InventoryTypeID != ''v0'' -- LỌC BỎ MÃ HÀNG CÓ LOẠI v0

        AND (@InventoryIDList IS NULL OR T_CUR.InventoryID = @InventoryIDList)

    GROUP BY T_CUR.InventoryID, T_ITEM.InventoryName, T_ITEM.I02ID, T_TYPE.InventoryTypeName, T_ITEM.I05ID,
        T_CUR.EndAmount, T_CUR.EndQuantity, T_LAST.MaxReceiptDate
    ORDER BY TotalCurrentValue DESC;
    ';

    -- Thực thi Dynamic SQL
    EXEC sp_executesql @SQL, 
                        N'@Today DATE, @InventoryIDList NVARCHAR(50), @CurrentMonth INT, @CurrentYear INT, @RiskThreshold DECIMAL(19, 4)', 
                        @Today, 
                        @InventoryIDList,
                        @CurrentMonth,
                        @CurrentYear,
                        @RiskThreshold;
END