CREATE PROCEDURE [dbo].[sp_Job_UpdateInventoryAging]
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Xóa sạch dữ liệu cũ
    TRUNCATE TABLE [dbo].[CACHE_INVENTORY_AGING];

    -- 2. Chèn dữ liệu mới từ SP gốc
    INSERT INTO [dbo].[CACHE_INVENTORY_AGING] (
        InventoryID, InventoryName, ItemCategory, InventoryTypeName, StockClass,
        TotalCurrentValue, TotalCurrentQuantity,
        Range_0_180_V, Range_181_360_V, Range_361_540_V, Range_541_720_V, Range_Over_720_V,
        Range_0_180_Q, Range_181_360_Q, Range_361_540_Q, Range_541_720_Q, Range_Over_720_Q,
        Risk_CLC_Value
    )
    EXEC [dbo].[sp_GetInventoryAging]; -- Gọi SP gốc nặng nề

    -- 3. Cập nhật thời gian
    UPDATE [dbo].[CACHE_INVENTORY_AGING] SET LastUpdated = GETDATE();
END;
