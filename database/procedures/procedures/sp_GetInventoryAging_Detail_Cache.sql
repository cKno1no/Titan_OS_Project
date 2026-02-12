
CREATE PROCEDURE [dbo].[sp_GetInventoryAging_Detail_Cache]
    @Filter NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- Đọc toàn bộ chi tiết từ bảng Cache để phục vụ trang danh sách
    SELECT * FROM [dbo].[CACHE_INVENTORY_AGING];
END;
