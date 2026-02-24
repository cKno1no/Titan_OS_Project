
CREATE PROCEDURE [dbo].[sp_KPI_Sales_GetMetrics]
    @TranYear INT,
    @TranMonth INT,
    @UserCode VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Actual_Sales_Total DECIMAL(18,2) = 0;
    DECLARE @Actual_Sales_NewCust DECIMAL(18,2) = 0;
    DECLARE @AR_Overdue_Rate FLOAT = 0;

    -- Biến cho khối Admin/Thư ký
    DECLARE @Actual_Support_Sales DECIMAL(18,2) = 0;
    DECLARE @Actual_Office_Sales DECIMAL(18,2) = 0;
    DECLARE @Late_Delivery_Count INT = 0;

    DECLARE @EOM DATE = EOMONTH(DATEFROMPARTS(@TranYear, @TranMonth, 1));
    DECLARE @12MonthsAgo DATE = DATEADD(month, -12, @EOM);

    -- ==============================================================================
    -- 1. DOANH SỐ TỔNG & VĂN PHÒNG (Dựa trên NVKD chốt đơn)
    -- ==============================================================================
    SELECT @Actual_Sales_Total = ISNULL(SUM(ConvertedAmount), 0) 
    FROM [OMEGA_STDD].[dbo].[GT9000] WITH (NOLOCK) 
    WHERE TranYear = @TranYear AND TranMonth = @TranMonth 
      AND DebitAccountID = '13111' AND CreditAccountID LIKE '5%' 
      AND SalesManID = @UserCode;
      
    SET @Actual_Office_Sales = @Actual_Sales_Total;
    
    -- ==============================================================================
    -- 2. DOANH SỐ HỖ TRỢ (Dựa trên OT2001 - Đơn do Thư ký thao tác)
    -- ==============================================================================
    SELECT @Actual_Support_Sales = ISNULL(SUM(H.ConvertedAmount), 0) 
    FROM [OMEGA_STDD].[dbo].[GT9000] H WITH (NOLOCK) 
    INNER JOIN [OMEGA_STDD].[dbo].[OT2001] O WITH (NOLOCK) ON H.OrderID = O.SOrderID
    WHERE H.TranYear = @TranYear AND H.TranMonth = @TranMonth 
      AND H.DebitAccountID = '13111' AND H.CreditAccountID LIKE '5%' 
      AND O.EmployeeID = @UserCode;

    -- ==============================================================================
    -- 3. DOANH SỐ KHÁCH HÀNG MỚI (Lọc khách chưa mua hoặc mua cách đây > 1 năm)
    -- ==============================================================================
    SELECT DISTINCT ObjectID INTO #CurrentMonthCusts 
    FROM [OMEGA_STDD].[dbo].[GT9000] WITH (NOLOCK) 
    WHERE TranYear = @TranYear AND TranMonth = @TranMonth 
      AND DebitAccountID = '13111' AND CreditAccountID LIKE '5%' 
      AND SalesManID = @UserCode;
      
    SELECT C.ObjectID, 
           MIN(H.VoucherDate) AS FirstPurchaseEver, 
           MAX(CASE WHEN H.VoucherDate < @12MonthsAgo THEN H.VoucherDate ELSE NULL END) AS LastPurchaseOld 
    INTO #CustHistory 
    FROM #CurrentMonthCusts C 
    JOIN [OMEGA_STDD].[dbo].[GT9000] H WITH (NOLOCK) ON C.ObjectID = H.ObjectID 
    WHERE H.DebitAccountID = '13111' AND H.CreditAccountID LIKE '5%' 
    GROUP BY C.ObjectID;
    
    SELECT @Actual_Sales_NewCust = ISNULL(SUM(H.ConvertedAmount), 0) 
    FROM [OMEGA_STDD].[dbo].[GT9000] H WITH (NOLOCK) 
    JOIN #CustHistory CH ON H.ObjectID = CH.ObjectID 
    WHERE H.TranYear = @TranYear AND H.TranMonth = @TranMonth 
      AND H.DebitAccountID = '13111' AND H.CreditAccountID LIKE '5%' 
      AND H.SalesManID = @UserCode 
      AND (CH.FirstPurchaseEver >= @12MonthsAgo OR DATEDIFF(day, CH.LastPurchaseOld, CH.FirstPurchaseEver) > 365);

    -- ==============================================================================
    -- 4. TỶ LỆ NỢ QUÁ HẠN (Đọc chuẩn xác từ bảng AR_AGING_SUMMARY & DTCL)
    -- ==============================================================================
    DECLARE @Total_Debt DECIMAL(18,2) = 0, @Overdue_Debt DECIMAL(18,2) = 0;
    
    SELECT 
        @Total_Debt = ISNULL(SUM(T1.TotalDebt), 0), 
        @Overdue_Debt = ISNULL(SUM(T1.TotalOverdueDebt), 0) 
    FROM [dbo].[CRM_AR_AGING_SUMMARY] T1 WITH (NOLOCK) 
    LEFT JOIN [dbo].[DTCL] T2 WITH (NOLOCK) ON T1.ObjectID = T2.[MA KH] AND T2.Nam = @TranYear 
    WHERE RTRIM(T2.[PHU TRACH DS]) = RTRIM(@UserCode);
    
    IF @Total_Debt > 0 
        SET @AR_Overdue_Rate = (@Overdue_Debt / @Total_Debt) * 100;

    -- ==============================================================================
    -- 5. CAM KẾT LEADTIME - GIAO HÀNG TRỄ (Admin / Thư ký xuất hàng)
    -- ==============================================================================
    SELECT @Late_Delivery_Count = COUNT(DISTINCT O.VoucherNo) 
    FROM [OMEGA_STDD].[dbo].[OT2001] O WITH (NOLOCK) 
    INNER JOIN [OMEGA_STDD].[dbo].[OT2002] OD WITH (NOLOCK) ON O.SOrderID = OD.SOrderID 
    INNER JOIN [OMEGA_STDD].[dbo].[WT2007] WD WITH (NOLOCK) ON OD.TransactionID = WD.OTransactionID 
    INNER JOIN [OMEGA_STDD].[dbo].[WT2006] W WITH (NOLOCK) ON WD.VoucherID = W.VoucherID 
    WHERE W.TranYear = @TranYear AND W.TranMonth = @TranMonth 
      AND W.VoucherTypeID IN ('XK', 'VC', 'PX') 
      AND O.EmployeeID = @UserCode 
      AND OD.Date01 IS NOT NULL 
      AND DATEDIFF(day, OD.Date01, W.VoucherDate) > 7;

    -- ==============================================================================
    -- 6. CHẤT LƯỢNG TƯ VẤN (WIN-RATE) - Kèm "Thỏa hiệp Lý do rớt"
    -- ==============================================================================
    DECLARE @WinQuotes FLOAT = 0;
    DECLARE @LostNoReason FLOAT = 0;
    DECLARE @LostWithReason FLOAT = 0;
    DECLARE @Quote_WinRate FLOAT = 0;

    SELECT 
        -- Đếm số BG đã WIN
        @WinQuotes = SUM(CASE WHEN ISNULL(C.[TINH_TRANG_BG], '') = 'WIN' THEN 1 ELSE 0 END),
        
        -- Đếm rớt KHÔNG có lý do (Phạt 100%)
        @LostNoReason = SUM(CASE WHEN ISNULL(C.[TINH_TRANG_BG], '') IN ('LOST', 'CANCEL') AND ISNULL(C.[LY_DO_THUA], '') = '' THEN 1 ELSE 0 END),
        
        -- Đếm rớt CÓ LÝ DO (Được giảm nhẹ chỉ tính 20%)
        @LostWithReason = SUM(CASE WHEN ISNULL(C.[TINH_TRANG_BG], '') IN ('LOST', 'CANCEL') AND ISNULL(C.[LY_DO_THUA], '') <> '' THEN 1 ELSE 0 END)
        
    FROM [OMEGA_STDD].[dbo].[OT2101] H WITH (NOLOCK)
    LEFT JOIN [dbo].[HD_CAP NHAT BAO GIA] C WITH (NOLOCK) ON H.QuotationNo = C.[MA_BAO_GIA]
    WHERE H.EmployeeID = @UserCode 
      AND H.TranYear = @TranYear AND H.TranMonth = @TranMonth;

    DECLARE @EffectiveTotal FLOAT = @WinQuotes + @LostNoReason + (@LostWithReason * 0.2);

    IF @EffectiveTotal > 0 
        SET @Quote_WinRate = (@WinQuotes / @EffectiveTotal) * 100.0;

    -- Dọn dẹp bảng tạm
    DROP TABLE #CurrentMonthCusts; 
    DROP TABLE #CustHistory;

    -- ==============================================================================
    -- XUẤT KẾT QUẢ ĐỂ PYTHON (SERVICE) BẮT LẤY
    -- ==============================================================================
    SELECT 
        ISNULL(@Actual_Sales_Total, 0) AS Actual_Sales_Total, 
        ISNULL(@Actual_Sales_NewCust, 0) AS Actual_Sales_NewCust, 
        ISNULL(@AR_Overdue_Rate, 0) AS AR_Overdue_Rate, 
        ISNULL(@Actual_Support_Sales, 0) AS Actual_Support_Sales, 
        ISNULL(@Actual_Office_Sales, 0) AS Actual_Office_Sales, 
        ISNULL(@Late_Delivery_Count, 0) AS Late_Delivery_Admin,
        ISNULL(@Quote_WinRate, 0) AS Quote_WinRate;
END;

GO
