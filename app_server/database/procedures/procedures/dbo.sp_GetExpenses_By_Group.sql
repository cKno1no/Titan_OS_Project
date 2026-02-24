
-- 1. [FIX] SP CHI TIẾT CHI PHÍ (Xử lý trùng lặp Ana03ID)
-- Logic: Lọc danh sách Ana03ID duy nhất trước khi Join để tránh nhân đôi số liệu
CREATE PROCEDURE [dbo].[sp_GetExpenses_By_Group]
    @Year INT,
    @ExcludeCode NVARCHAR(50)
AS
BEGIN
    -- Bước 1: Tạo bảng ánh xạ duy nhất (Distinct Map)
    -- Vì 1 Ana03ID có thể thuộc nhiều BudgetCode, ta chỉ cần biết nó thuộc ReportGroup nào
    WITH UniqueMap AS (
        SELECT DISTINCT ERP_Ana03ID, ReportGroup 
        FROM [CRM_STDD].[dbo].[BUDGET_MASTER]
        WHERE ERP_Ana03ID IS NOT NULL AND ERP_Ana03ID <> ''
    )
    
    SELECT 
        ISNULL(M.ReportGroup, 'Khác') as Label,
        SUM(T1.ConvertedAmount) as Value
    FROM [OMEGA_STDD].[dbo].[GT9000] T1
    LEFT JOIN UniqueMap M ON T1.Ana03ID = M.ERP_Ana03ID
    WHERE T1.TranYear = @Year
      AND T1.Ana03ID IS NOT NULL 
      AND T1.Ana03ID <> ''
      AND T1.Ana03ID <> @ExcludeCode
      -- Thêm điều kiện lọc tài khoản chi phí nếu cần (64*, 811*) để chính xác hơn
      AND (T1.DebitAccountID LIKE '6%' OR T1.DebitAccountID LIKE '8%') 
    GROUP BY ISNULL(M.ReportGroup, 'Khác')
    ORDER BY Value DESC;
END

GO
