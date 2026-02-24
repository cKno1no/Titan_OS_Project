
-- 2. SP LẤY CHI TIẾT CHI PHÍ (Theo Ana03ID)
-- Logic: Loại trừ Ana03ID rỗng và mã loại trừ (VD: CP2014)
CREATE PROCEDURE [dbo].[sp_GetExpenses_By_Ana03]
    @Year INT,
    @ExcludeCode NVARCHAR(50) -- Mã cần loại trừ (VD: CP2014)
AS
BEGIN
    SELECT 
        T1.Ana03ID,
        ISNULL(M.BudgetName, T1.Ana03ID) as ExpenseName,
        SUM(T1.ConvertedAmount) as Amount
    FROM [OMEGA_STDD].[dbo].[GT9000] T1
    LEFT JOIN [CRM_STDD].[dbo].[BUDGET_MASTER] M ON T1.Ana03ID = M.ERP_Ana03ID
    WHERE T1.TranYear = @Year
      AND (T1.DebitAccountID LIKE '64%' OR T1.DebitAccountID LIKE '811%')
      -- [QUAN TRỌNG] Logic lọc Chi phí
      AND T1.Ana03ID IS NOT NULL 
      AND T1.Ana03ID <> ''
      AND T1.Ana03ID <> @ExcludeCode
    GROUP BY T1.Ana03ID, M.BudgetName
    ORDER BY Amount DESC;
END

GO
