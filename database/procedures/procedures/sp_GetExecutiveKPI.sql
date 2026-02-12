CREATE PROCEDURE sp_GetExecutiveKPI
    @TranYear INT,
    @TranMonth INT
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Biến bảng tạm để tính toán nhanh
    DECLARE @SalesYTD FLOAT = 0, @COGS_YTD FLOAT = 0, @Expenses_YTD FLOAT = 0;
    DECLARE @Budget_YTD FLOAT = 0;
    DECLARE @VipProfit FLOAT = 0, @VipCount INT = 0;
    
    -- 2. Tính Doanh số & Giá vốn & Chi phí (Từ sổ cái GT9000)
    -- Gom nhóm 1 lần để scan bảng ít nhất có thể
    SELECT 
        @SalesYTD = SUM(CASE WHEN CreditAccountID LIKE '511%' THEN ConvertedAmount ELSE 0 END),
        @COGS_YTD = SUM(CASE WHEN DebitAccountID LIKE '632%' THEN ConvertedAmount ELSE 0 END),
        @Expenses_YTD = SUM(CASE 
            WHEN (DebitAccountID LIKE '6%' OR DebitAccountID LIKE '8%') 
                 AND Ana03ID IS NOT NULL AND Ana03ID <> 'CP2014' -- Loại trừ kết chuyển
            THEN ConvertedAmount ELSE 0 END)
    FROM [OMEGA_STDD].[dbo].[GT9000] 
    WHERE TranYear = @TranYear AND TranMonth <= @TranMonth;

    -- 3. Tính Ngân sách (Budget Plan)
    SELECT @Budget_YTD = SUM(BudgetAmount)
    FROM BUDGET_PLAN 
    WHERE FiscalYear = @TranYear AND [Month] <= @TranMonth;

    -- 4. Tính Cross-sell (VIP Customers)
    -- Logic: KH mua >= 10 nhóm hàng (I04ID) trong 12 tháng qua
    ;WITH VIP_List AS (
        SELECT T1.ObjectID
        FROM [OMEGA_STDD].[dbo].[GT9000] T1
        INNER JOIN [OMEGA_STDD].[dbo].[IT1302] T2 ON T1.InventoryID = T2.InventoryID
        WHERE T1.VoucherDate >= DATEADD(day, -365, GETDATE()) 
          AND T2.I04ID IS NOT NULL AND T2.I04ID <> ''
          AND (T1.CreditAccountID LIKE '511%' OR T1.DebitAccountID LIKE '632%')
        GROUP BY T1.ObjectID
        HAVING COUNT(DISTINCT T2.I04ID) >= 10
    )
    SELECT 
        @VipCount = COUNT(DISTINCT V.ObjectID),
        @VipProfit = SUM(CASE WHEN T.CreditAccountID LIKE '511%' THEN T.ConvertedAmount ELSE 0 END) -
                     SUM(CASE WHEN T.DebitAccountID LIKE '632%' THEN T.ConvertedAmount ELSE 0 END)
    FROM [OMEGA_STDD].[dbo].[GT9000]  T
    INNER JOIN VIP_List V ON T.ObjectID = V.ObjectID
    WHERE T.TranYear = @TranYear AND T.TranMonth <= @TranMonth;

    -- 5. Lấy Rủi ro Nợ & Tồn kho (Từ View có sẵn)
    -- Trả về Result Set duy nhất
    SELECT 
        ISNULL(@SalesYTD, 0) AS Sales_YTD,
        ISNULL(@SalesYTD - @COGS_YTD, 0) AS GrossProfit_YTD,
        ISNULL(@Expenses_YTD, 0) AS TotalExpenses_YTD,
        ISNULL(@Budget_YTD, 0) AS BudgetPlan_YTD,
        ISNULL(@VipProfit, 0) AS CrossSellProfit_YTD,
        ISNULL(@VipCount, 0) AS CrossSellCustCount,
        
        -- Số liệu rủi ro (Subquery nhanh từ View)
        (SELECT ISNULL(SUM(TotalOverdueDebt), 0) FROM CRM_AR_AGING_SUMMARY) AS AR_Overdue,
        (SELECT ISNULL(SUM(Debt_Over_180), 0) FROM CRM_AR_AGING_SUMMARY) AS AR_Risk,
        (SELECT ISNULL(SUM(TotalOverdueDebt), 0) FROM CRM_AP_AGING_SUMMARY WHERE DebtType = 'SUPPLIER') AS AP_Overdue,
        (SELECT ISNULL(SUM(Debt_Over_180), 0) FROM CRM_AP_AGING_SUMMARY WHERE DebtType = 'SUPPLIER') AS AP_Risk
END;
