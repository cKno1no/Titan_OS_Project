/*
ALTER SP 3: BÁO CÁO DỰ PHÒNG KHÁCH HÀNG (ĐÃ TỐI ƯU)
- Sửa lỗi: Đọc Varchar05/I01ID/I02ID trực tiếp từ View [cite: image_647f61.jpg]
- Req 2, 3, 4, 5
*/
CREATE PROCEDURE dbo.sp_GetCustomerReplenishmentSuggest
    @ObjectID NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    -- Tối ưu hóa CTE: Đọc trực tiếp từ View đã có đủ cột
    WITH StockStatus AS (
        SELECT 
            T.Varchar05,
            ISNULL(MIN(T.I02ID), 'ZZZ') AS I02ID_Group,
            SUM(ISNULL(T.Ton, 0)) AS CurrentStock,
            SUM(ISNULL(T.con, 0)) AS IncomingStock
        FROM 
            [OMEGA_STDD].[dbo].[CRM_TON KHO BACK ORDER] AS T
        WHERE 
            T.I01ID IN ('A', 'B', 'D') -- Lọc trực tiếp trên View
        GROUP BY 
            T.Varchar05
    )
    
    SELECT 
        V_CUST.Varchar05 AS [NhomHang],
        (V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days AS NhuCauTrongLeadTime_Goc,
        ((V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days) 
        - (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0)) AS [LuongThieuDu],
        CASE
            WHEN (V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days < 10 
            THEN (V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days
            ELSE CEILING(((V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days) / 10.0) * 10
        END AS [DiemTaiDatROP],
        (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0)) AS [TonBO],
        V_CUST.CustomerMonthlyVelocity AS [TieuHaoThang],
        CASE 
            WHEN (((V_CUST.CustomerMonthlyVelocity / 30.4) * V_GROUP.LeadTime_Days) 
                  - (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0))) > 0 THEN 1
            ELSE 2
        END AS Deficit_Group,
        ISNULL(S.I02ID_Group, 'ZZZ') AS NganhHang_I02ID
        , ISNULL(S.CurrentStock, 0) AS TonKhoHienTai
        , ISNULL(S.IncomingStock, 0) AS HangDangVe
        , V_GROUP.LeadTime_Days
    FROM 
        dbo.VELOCITY_SKU_CUSTOMER AS V_CUST
    JOIN 
        dbo.VELOCITY_SKU_GROUP AS V_GROUP ON V_CUST.Varchar05 = V_GROUP.Varchar05
    LEFT JOIN 
        StockStatus AS S ON V_CUST.Varchar05 = S.Varchar05
    WHERE 
        V_CUST.ObjectID = @ObjectID
        AND V_CUST.Flag = 'Recurring'
        AND V_CUST.CustomerMonthlyVelocity > 0
    ORDER BY 
        /* Req 2: Sắp xếp */
        Deficit_Group ASC,
        NganhHang_I02ID ASC,
        [NhomHang] ASC;
        
    SET NOCOUNT OFF;
END;