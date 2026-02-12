
/*
SP MỚI: Lấy gợi ý dự phòng cho Portal (Tối ưu hiệu suất)
- Lọc 1: Chỉ KH có DS đăng ký > 300tr
- Lọc 2: Loại bỏ hàng Nhóm X hoặc Null
- Lọc 3: Chỉ lấy SL gợi ý > 2
*/
CREATE PROCEDURE [dbo].[sp_GetPortalReplenishment]
    @UserCode NVARCHAR(50),
    @Year INT
AS
BEGIN
    SET NOCOUNT ON;

    -- BƯỚC 1: Lấy danh sách Khách hàng "VIP" (DS Đăng ký > 300tr)
    -- Giúp giảm scope tính toán ngay từ đầu
    SELECT [MA KH], [TEN kh]
    INTO #VipCustomers
    FROM [dbo].[DTCL]
    WHERE [Nam] = @Year
      AND [PHU TRACH DS] = @UserCode
      AND [DK] > 300000000; -- Yêu cầu 1

    -- BƯỚC 2: Tính toán Tồn kho & Đang về (Chỉ cho các mã hàng liên quan)
    -- Lọc bỏ hàng 'X' và Null tại nguồn
    WITH StockStatus AS (
        SELECT 
            T.Varchar05,
            SUM(ISNULL(T.Ton, 0)) AS CurrentStock,
            SUM(ISNULL(T.con, 0)) AS IncomingStock
        FROM [OMEGA_STDD].[dbo].[CRM_TON KHO BACK ORDER] AS T
        WHERE T.I01ID IN ('A', 'B', 'D')
          AND ISNULL(T.I02ID, '') NOT LIKE '%X%' -- Yêu cầu 2: Không chứa X
          AND T.I02ID IS NOT NULL                -- Yêu cầu 2: Không Null
        GROUP BY T.Varchar05
    )

    -- BƯỚC 3: Tính toán Velocity & Gợi ý
    SELECT TOP 20
        V_CUST.Varchar05 AS InventoryItemID,
        V_CUST.Varchar05 AS ItemName,
        CAST(
            ( (V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days ) 
            - (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0)) 
        AS DECIMAL(18, 0)) AS QuantitySuggestion,
        V_CUST.ObjectID AS CustomerID,
        C.[TEN kh] AS CustomerName
    FROM dbo.VELOCITY_SKU_CUSTOMER AS V_CUST
    -- Chỉ Join với KH VIP
    INNER JOIN #VipCustomers C ON V_CUST.ObjectID = C.[MA KH]
    JOIN dbo.VELOCITY_SKU_GROUP AS V_GROUP ON V_CUST.Varchar05 = V_GROUP.Varchar05
    LEFT JOIN StockStatus AS S ON V_CUST.Varchar05 = S.Varchar05
    WHERE 
        V_CUST.Flag = 'Recurring'
        AND V_CUST.CustomerMonthlyVelocity > 0
        -- Yêu cầu 3: SL Gợi ý > 2
        AND (
            ( (V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days ) 
            - (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0))
        ) > 2
    ORDER BY QuantitySuggestion DESC;

    -- Dọn dẹp
    DROP TABLE #VipCustomers;
    SET NOCOUNT OFF;
END;
