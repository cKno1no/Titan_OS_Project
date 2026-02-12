/*
ALTER SP 4: SP TẢI CHI TIẾT (ĐÃ SỬA LỖI)
- Sửa lỗi: Đọc trực tiếp từ View, KHÔNG CẦN JOIN
*/
CREATE PROCEDURE dbo.sp_GetReplenishmentGroupDetails
    @Varchar05 NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT 
        InventoryID,
        InventoryName,
        ISNULL(Ton, 0) AS TonKhoHienTai,
        ISNULL(con, 0) AS HangDangVe
    FROM 
        /* Đọc trực tiếp từ View đã có đủ cột [cite: image_6387dd.jpg] */
        [OMEGA_STDD].[dbo].[CRM_TON KHO BACK ORDER]
    WHERE 
        Varchar05 = @Varchar05
        AND I01ID IN ('A', 'B', 'D')
    ORDER BY 
        InventoryID;

    SET NOCOUNT OFF;
END;