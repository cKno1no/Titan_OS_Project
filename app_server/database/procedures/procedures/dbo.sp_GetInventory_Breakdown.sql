
-- 4. SP CHI TIẾT TỒN KHO
-- Logic: Mới (<180), CLC (180-720), Cũ (>720 - Tức > 2 năm)
CREATE PROCEDURE [dbo].[sp_GetInventory_Breakdown]
AS
BEGIN
    -- Gọi lại SP gốc để lấy dữ liệu thô, sau đó Group lại
    -- Lưu ý: Cần tạo bảng tạm để hứng dữ liệu từ SP
    CREATE TABLE #TmpInv (
        InventoryID NVARCHAR(50), 
        Range_0_180_V DECIMAL(18,2),
        Range_181_360_V DECIMAL(18,2),
        Range_361_540_V DECIMAL(18,2),
        Range_541_720_V DECIMAL(18,2),
        Range_Over_720_V DECIMAL(18,2),
        TotalValue DECIMAL(18,2)
        -- Thêm các cột khác nếu SP gốc trả về nhiều hơn
    )
    
    -- Giả sử SP gốc trả về đúng các cột này. Nếu không, cần điều chỉnh INSERT
    INSERT INTO #TmpInv (InventoryID, Range_0_180_V, Range_181_360_V, Range_361_540_V, Range_541_720_V, Range_Over_720_V, TotalValue)
    EXEC [dbo].[sp_GetInventoryAging] @WareHouseID = NULL

    SELECT 
        'Hàng Mới (< 6 tháng)' as Label, SUM(Range_0_180_V) as Amount FROM #TmpInv
    UNION ALL
    SELECT 
        'Chậm Luân Chuyển (6T - 2 Năm)' as Label, SUM(Range_181_360_V + Range_361_540_V + Range_541_720_V) as Amount FROM #TmpInv
    UNION ALL
    SELECT 
        'Tồn Kho Lâu (> 2 Năm)' as Label, SUM(Range_Over_720_V) as Amount FROM #TmpInv

    DROP TABLE #TmpInv
END

GO
