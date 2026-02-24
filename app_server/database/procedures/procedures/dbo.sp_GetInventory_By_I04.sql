
-- 4. [NEW] SP TỒN KHO THEO I04ID (Drill-down Inventory)
CREATE PROCEDURE [dbo].[sp_GetInventory_By_I04]
AS
BEGIN
    -- Gọi SP tính tuổi kho gốc để lấy dữ liệu thô
    CREATE TABLE #TmpInv (
        InventoryID NVARCHAR(50), 
        Range_0_180_V DECIMAL(18,2), Range_181_360_V DECIMAL(18,2), 
        Range_361_540_V DECIMAL(18,2), Range_541_720_V DECIMAL(18,2), 
        Range_Over_720_V DECIMAL(18,2), TotalValue DECIMAL(18,2)
    )
    INSERT INTO #TmpInv EXEC [dbo].[sp_GetInventoryAging] @WareHouseID = NULL

    -- Gộp theo I04ID
    SELECT 
        T2.I04ID as Label,
        SUM(T1.TotalValue) as TotalStock,
        SUM(T1.Range_Over_720_V) as Value -- Lấy giá trị > 2 năm làm Value chính để cảnh báo Rủi ro
    FROM #TmpInv T1
    INNER JOIN [OMEGA_STDD].[dbo].[IT1302] T2 ON T1.InventoryID = T2.InventoryID
    GROUP BY T2.I04ID
    HAVING SUM(T1.TotalValue) > 0
    ORDER BY TotalStock DESC -- Mặc định sort theo tổng tồn kho

    DROP TABLE #TmpInv
END

GO
