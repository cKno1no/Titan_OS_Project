
-- =============================================
-- Author:      Titan AI
-- Description: Phân tích Cơ cấu Nhóm hàng & Lãi biên (Gross Margin) theo Khách hàng
-- Logic:       Đồng bộ với CEO Cockpit (Rev=511%, Cost=632%)
-- =============================================
CREATE PROCEDURE [dbo].[sp_GetCustomerCategoryAnalysis]
    @ObjectID NVARCHAR(50),
    @Year INT
AS
BEGIN
    SET NOCOUNT ON;

    -- Biến tạm để giữ cấu hình tài khoản (tương tự config.py)
    DECLARE @AccRevenue NVARCHAR(10) = '511%';
    DECLARE @AccCost NVARCHAR(10) = '632%';

    SELECT TOP 20
        T2.I04ID AS CategoryID,
        ISNULL(T3.TEN, T2.I04ID) AS CategoryName,

        -- 1. Doanh thu (Credit 511)
        SUM(CASE 
            WHEN T1.CreditAccountID LIKE @AccRevenue THEN T1.ConvertedAmount 
            ELSE 0 
        END) AS Revenue,

        -- 2. Giá vốn (Debit 632)
        SUM(CASE 
            WHEN T1.DebitAccountID LIKE @AccCost THEN T1.ConvertedAmount 
            ELSE 0 
        END) AS Cost,

        -- 3. Lợi nhuận gộp (Revenue - Cost)
        SUM(CASE WHEN T1.CreditAccountID LIKE @AccRevenue THEN T1.ConvertedAmount ELSE 0 END) - 
        SUM(CASE WHEN T1.DebitAccountID LIKE @AccCost THEN T1.ConvertedAmount ELSE 0 END) AS GrossProfit

    FROM [OMEGA_STDD].[dbo].[GT9000] T1 WITH (NOLOCK)
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1302] T2 WITH (NOLOCK) ON T1.InventoryID = T2.InventoryID
    LEFT JOIN [NOI DUNG HD] T3 WITH (NOLOCK) ON T2.I04ID = T3.LOAI

    WHERE T1.ObjectID = @ObjectID
      AND T1.TranYear = @Year
      AND T1.InventoryID IS NOT NULL -- Chỉ lấy các dòng có dính tới hàng hóa
      AND (
          T1.CreditAccountID LIKE @AccRevenue 
          OR T1.DebitAccountID LIKE @AccCost
      )

    GROUP BY T2.I04ID, T3.TEN
    
    -- Chỉ lấy các nhóm có phát sinh doanh thu hoặc giá vốn
    HAVING SUM(CASE WHEN T1.CreditAccountID LIKE @AccRevenue THEN T1.ConvertedAmount ELSE 0 END) > 0 
        OR SUM(CASE WHEN T1.DebitAccountID LIKE @AccCost THEN T1.ConvertedAmount ELSE 0 END) > 0
        
    ORDER BY Revenue DESC;
END;
