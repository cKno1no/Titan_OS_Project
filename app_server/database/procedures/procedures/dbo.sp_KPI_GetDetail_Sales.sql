
CREATE PROCEDURE [dbo].[sp_KPI_GetDetail_Sales]
    @CriteriaID VARCHAR(50),
    @UserCode VARCHAR(50),
    @TranYear INT,
    @TranMonth INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @EOM DATE = EOMONTH(DATEFROMPARTS(@TranYear, @TranMonth, 1));
    DECLARE @12MonthsAgo DATE = DATEADD(month, -12, @EOM);

    -- ==============================================================================
    -- 1. Thành tích Doanh số Tổng (KPI_KD_01)
    -- ==============================================================================
    IF @CriteriaID = 'KPI_KD_01'
    BEGIN
        SELECT 
            ISNULL(KH.ShortObjectName, H.ObjectID) AS KhachHang,
            COUNT(DISTINCT H.VoucherNo) AS SoLuongHD,
            SUM(H.ConvertedAmount) AS DoanhSo
        FROM [OMEGA_STDD].[dbo].[GT9000] H WITH (NOLOCK)
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] KH WITH (NOLOCK) ON H.ObjectID = KH.ObjectID
        WHERE H.TranYear = @TranYear AND H.TranMonth = @TranMonth
          AND H.DebitAccountID = '13111' AND H.CreditAccountID LIKE '5%'
          AND H.SalesManID = @UserCode
        GROUP BY ISNULL(KH.ShortObjectName, H.ObjectID)
        ORDER BY SUM(H.ConvertedAmount) DESC;
    END

    -- ==============================================================================
    -- 2. Phát triển Khách hàng mới (KPI_KD_02)
    -- ==============================================================================
    ELSE IF @CriteriaID = 'KPI_KD_02'
    BEGIN
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

        SELECT 
            ISNULL(KH.ShortObjectName, H.ObjectID) AS KhachHang,
            COUNT(DISTINCT H.VoucherNo) AS SoLuongHD,
            SUM(H.ConvertedAmount) AS DoanhSo
        FROM [OMEGA_STDD].[dbo].[GT9000] H WITH (NOLOCK)
        JOIN #CustHistory CH ON H.ObjectID = CH.ObjectID
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] KH WITH (NOLOCK) ON H.ObjectID = KH.ObjectID
        WHERE H.TranYear = @TranYear AND H.TranMonth = @TranMonth 
          AND H.DebitAccountID = '13111' AND H.CreditAccountID LIKE '5%' 
          AND H.SalesManID = @UserCode
          AND (CH.FirstPurchaseEver >= @12MonthsAgo OR DATEDIFF(day, CH.LastPurchaseOld, CH.FirstPurchaseEver) > 365)
        GROUP BY ISNULL(KH.ShortObjectName, H.ObjectID)
        ORDER BY SUM(H.ConvertedAmount) DESC;

        DROP TABLE #CurrentMonthCusts; 
        DROP TABLE #CustHistory;
    END
    
    -- ==============================================================================
    -- 3. Chi tiết Nợ Quá Hạn (KPI_KD_03)
    -- Đọc từ bảng AR_AGING_SUMMARY để đảm bảo khớp 100% với màn hình Công nợ
    -- ==============================================================================
    ELSE IF @CriteriaID = 'KPI_KD_03'
    BEGIN
        SELECT 
            T1.ObjectName AS KhachHang,
            T1.TotalDebt AS TongNo,
            T1.TotalOverdueDebt AS NoQuaHan
        FROM [dbo].[CRM_AR_AGING_SUMMARY] T1 WITH (NOLOCK)
        LEFT JOIN [dbo].[DTCL] T2 WITH (NOLOCK) ON T1.ObjectID = T2.[MA KH] AND T2.Nam = @TranYear
        WHERE RTRIM(T2.[PHU TRACH DS]) = RTRIM(@UserCode)
          AND T1.TotalDebt > 0
        ORDER BY T1.TotalOverdueDebt DESC, T1.TotalDebt DESC;
    END
END;

GO
