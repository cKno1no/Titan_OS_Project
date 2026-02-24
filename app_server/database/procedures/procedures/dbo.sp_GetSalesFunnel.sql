CREATE PROCEDURE sp_GetSalesFunnel
    @DateFrom DATE,
    @DateTo DATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Số lượng Chào giá
    DECLARE @CountQuotes INT;
    SELECT @CountQuotes = COUNT(*) FROM [OMEGA_STDD].[dbo].[OT2001] WHERE OrderDate BETWEEN @DateFrom AND @DateTo;

    -- 2. Số lượng Đơn hàng
    DECLARE @CountOrders INT;
    SELECT @CountOrders = COUNT(*) FROM [OMEGA_STDD].[dbo].[OT2001] WHERE OrderDate BETWEEN @DateFrom AND @DateTo;

    -- 3. Doanh số thực tế (Tỷ VNĐ)
    DECLARE @Revenue DECIMAL(18, 2);
    SELECT @Revenue = SUM(ConvertedAmount) / 1000000000.0 -- Chia tỷ
    FROM [OMEGA_STDD].[dbo].[GT9000] 
    WHERE VoucherDate BETWEEN @DateFrom AND @DateTo 
      AND CreditAccountID LIKE '511%';

    -- Trả về bảng kết quả
    SELECT 'Quotes' AS Stage, CAST(@CountQuotes AS FLOAT) AS Value
    UNION ALL
    SELECT 'Orders' AS Stage, CAST(@CountOrders AS FLOAT) AS Value
    UNION ALL
    SELECT 'Revenue' AS Stage, ISNULL(@Revenue, 0) AS Value;
END;

GO
