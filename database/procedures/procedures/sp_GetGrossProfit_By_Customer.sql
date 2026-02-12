
-- 2. [NEW] SP KPI LỢI NHUẬN GỘP (Drill-down Top 30 Khách hàng)
CREATE PROCEDURE [dbo].[sp_GetGrossProfit_By_Customer]
    @Year INT
AS
BEGIN
    SELECT TOP 30
        T1.ObjectID,
        ISNULL(T2.ShortObjectName, T2.ObjectName) as Label, -- Tên hiển thị
        
        SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) as Revenue,
        
        (SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) -
         SUM(CASE WHEN T1.DebitAccountID LIKE '632%' THEN T1.ConvertedAmount ELSE 0 END)) as Value -- Gross Profit
         
    FROM [OMEGA_STDD].[dbo].[GT9000] T1
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] T2 ON T1.ObjectID = T2.ObjectID
    WHERE T1.TranYear = @Year
      AND T1.OTransactionID IS NOT NULL -- Chỉ lấy hóa đơn chính thức
    GROUP BY T1.ObjectID, T2.ShortObjectName, T2.ObjectName
    HAVING SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) > 0
    ORDER BY Value DESC; -- Sắp xếp theo Lợi nhuận
END
