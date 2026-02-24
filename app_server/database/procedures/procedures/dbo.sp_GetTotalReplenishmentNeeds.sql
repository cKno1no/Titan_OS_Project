/*
ALTER SP 2: BÁO CÁO DỰ PHÒNG TỔNG THỂ (ĐÃ TỐI ƯU)
- Sửa lỗi: Đọc Varchar05/I01ID/I02ID trực tiếp từ View [cite: image_647f61.jpg]
- Req 2, 3, 4, 5
*/
CREATE PROCEDURE dbo.sp_GetTotalReplenishmentNeeds
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
        V.Varchar05 AS [NhomHang],
        
        /* Req 2a: Cấp nhóm (Cần đặt / Không cần) */
        CASE 
            WHEN (V.ROP - (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0))) > 0 THEN 1
            ELSE 2
        END AS Deficit_Group,
        
        /* Req 2b: Cấp nhóm (Ngành hàng) */
        ISNULL(S.I02ID_Group, 'ZZZ') AS NganhHang_I02ID,

        /* Req 3: Lượng thiếu/ Dư */
        (V.ROP - (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0))) AS [LuongThieuDu],
        
        /* Req 4: Làm tròn ROP */
        CASE
            WHEN V.ROP < 10 THEN V.ROP
            ELSE CEILING(V.ROP / 10.0) * 10
        END AS [DiemTaiDatROP],
        
        /* Req 3: Tồn-BO */
        (ISNULL(S.CurrentStock, 0) + ISNULL(S.IncomingStock, 0)) AS [TonBO],
        
        /* Req 3: Tiêu hao (Tháng) */
        V.TotalMonthlyVelocity AS [TieuHaoThang]

        /* ----- Các cột dữ liệu nền để JS sử dụng ----- */
        , ISNULL(S.CurrentStock, 0) AS TonKhoHienTai
        , ISNULL(S.IncomingStock, 0) AS HangDangVe
        , V.ROP AS ROP_Goc
    FROM 
        dbo.VELOCITY_SKU_GROUP AS V
    LEFT JOIN 
        StockStatus AS S ON V.Varchar05 = S.Varchar05
    WHERE 
        V.ROP > 0 
    ORDER BY
        /* Req 2: Sắp xếp */
        Deficit_Group ASC,      -- (a) Ưu tiên Cần đặt (1) lên trước
        NganhHang_I02ID ASC,    -- (b) Sort theo Ngành hàng (I02ID)
        [NhomHang] ASC;         -- (c) Sort theo Nhóm hàng (Varchar05)

    SET NOCOUNT OFF;
END;
GO
