
-- 1. Cập nhật SP LẤY DOANH SỐ (Thêm điều kiện OTransactionID IS NOT NULL)
CREATE PROCEDURE [dbo].[sp_GetSalesPerformance_By_I04]
    @Year INT
AS
BEGIN
    SELECT 
        T2.I04ID,
        ISNULL(T3.TEN, T2.I04ID) as GroupName,
        SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) as Revenue,
        SUM(CASE WHEN T1.DebitAccountID LIKE '632%' THEN T1.ConvertedAmount ELSE 0 END) as COGS
    FROM [OMEGA_STDD].[dbo].[GT9000] T1
    INNER JOIN [OMEGA_STDD].[dbo].[IT1302] T2 ON T1.InventoryID = T2.InventoryID
    LEFT JOIN [CRM_STDD].[dbo].[NOI DUNG HD] T3 ON T2.I04ID = T3.LOAI
    WHERE T1.TranYear = @Year
      AND T1.OTransactionID IS NOT NULL -- [NEW] Chỉ lấy giao dịch có kết thừa từ Đơn hàng
    GROUP BY T2.I04ID, T3.TEN
    HAVING SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) > 0
    ORDER BY Revenue DESC;
END
