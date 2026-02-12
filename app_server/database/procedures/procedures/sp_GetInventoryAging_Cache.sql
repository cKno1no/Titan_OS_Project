
CREATE PROCEDURE [dbo].[sp_GetInventoryAging_Cache]
    @Filter NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- TRẢ VỀ 2 BẢNG KẾT QUẢ (RESULT SETS)

    -- BẢNG 1: TỔNG HỢP CHO BIỂU ĐỒ (Chỉ 1 dòng duy nhất hoặc 5 dòng phân loại)
    SELECT 
        SUM(Range_0_180_V) AS [Safe],
        SUM(Range_181_360_V) AS [Stable],
        SUM(Range_361_540_V + Range_541_720_V) AS [Slow],
        SUM(Range_Over_720_V - ISNULL(Risk_CLC_Value, 0)) AS [LongTerm],
        SUM(ISNULL(Risk_CLC_Value, 0)) AS [Risk]
    FROM [dbo].[CACHE_INVENTORY_AGING];

    -- BẢNG 2: CHI TIẾT TOP 20 NHÓM HÀNG (Để làm Drill-down, thay vì trả về 11k dòng)
    -- Lấy 3 ký tự đầu của InventoryID làm GroupID
    SELECT TOP 20
        LEFT(InventoryID, 3) AS GroupID,
        SUM(Range_0_180_V) AS [Safe],
        SUM(Range_181_360_V) AS [Stable],
        SUM(Range_361_540_V + Range_541_720_V) AS [Slow],
        SUM(Range_Over_720_V - ISNULL(Risk_CLC_Value, 0)) AS [LongTerm],
        SUM(ISNULL(Risk_CLC_Value, 0)) AS [Risk],
        SUM(TotalCurrentValue) AS TotalValue
    FROM [dbo].[CACHE_INVENTORY_AGING]
    GROUP BY LEFT(InventoryID, 3)
    ORDER BY TotalValue DESC;
END;
