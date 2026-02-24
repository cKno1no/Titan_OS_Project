
CREATE PROCEDURE [dbo].[sp_KPI_GetDetail_Admin]
    @CriteriaID VARCHAR(50), 
    @UserCode VARCHAR(50), 
    @TranYear INT, 
    @TranMonth INT
AS
BEGIN
    SET NOCOUNT ON;

    -- ==============================================================================
    -- 1. Doanh số Hỗ trợ (KPI_TK_01) 
    -- Tính theo đơn hàng (OT2001) do Thư ký thao tác nhập liệu
    -- ==============================================================================
    IF @CriteriaID = 'KPI_TK_01'
    BEGIN
        SELECT 
            O.SalesManID AS SalesChinh,
            ISNULL(KH.ShortObjectName, H.ObjectID) AS KhachHang,
            COUNT(DISTINCT H.VoucherNo) AS SoLuongHD,
            SUM(H.ConvertedAmount) AS DoanhSo
        FROM [OMEGA_STDD].[dbo].[GT9000] H WITH (NOLOCK)
        INNER JOIN [OMEGA_STDD].[dbo].[OT2001] O WITH (NOLOCK) ON H.OrderID = O.SOrderID
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] KH WITH (NOLOCK) ON H.ObjectID = KH.ObjectID
        WHERE H.TranYear = @TranYear AND H.TranMonth = @TranMonth
          AND H.DebitAccountID = '13111' AND H.CreditAccountID LIKE '5%'
          AND O.EmployeeID = @UserCode
        GROUP BY O.SalesManID, ISNULL(KH.ShortObjectName, H.ObjectID)
        ORDER BY SUM(H.ConvertedAmount) DESC;
    END

    -- ==============================================================================
    -- 2. Doanh số Kênh Văn phòng (KPI_TK_02)
    -- Thư ký tự chốt đơn, để tên mình ở trường NVKD
    -- ==============================================================================
    ELSE IF @CriteriaID = 'KPI_TK_02'
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
    -- 3. Cam kết Leadtime - Giao hàng trễ (KPI_TK_03)
    -- ==============================================================================
    ELSE IF @CriteriaID = 'KPI_TK_03'
    BEGIN
        SELECT 
            O.VoucherNo AS SoDonHang,
            ISNULL(KH.ShortObjectName, O.ObjectID) AS KhachHang,
            CONVERT(VARCHAR, OD.Date01, 103) AS NgayYeuCau,
            CONVERT(VARCHAR, W.VoucherDate, 103) AS NgayThucXuat,
            DATEDIFF(day, OD.Date01, W.VoucherDate) AS SoNgayTre
        FROM [OMEGA_STDD].[dbo].[OT2001] O WITH (NOLOCK)
        INNER JOIN [OMEGA_STDD].[dbo].[OT2002] OD WITH (NOLOCK) ON O.SOrderID = OD.SOrderID
        INNER JOIN [OMEGA_STDD].[dbo].[WT2007] WD WITH (NOLOCK) ON OD.TransactionID = WD.OTransactionID
        INNER JOIN [OMEGA_STDD].[dbo].[WT2006] W WITH (NOLOCK) ON WD.VoucherID = W.VoucherID
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] KH WITH (NOLOCK) ON O.ObjectID = KH.ObjectID
        WHERE W.TranYear = @TranYear AND W.TranMonth = @TranMonth
          AND W.VoucherTypeID IN ('XK', 'VC', 'PX')
          AND O.EmployeeID = @UserCode
          AND OD.Date01 IS NOT NULL
          AND DATEDIFF(day, OD.Date01, W.VoucherDate) > 7
        ORDER BY SoNgayTre DESC;
    END

    -- ==============================================================================
    -- 4. Chất lượng Tư vấn Win-rate (KPI_TK_04) 
    -- Map với bảng HD_CAP NHAT BAO GIA để lấy lý do rớt
    -- ==============================================================================
    ELSE IF @CriteriaID = 'KPI_TK_04'
    BEGIN
        SELECT 
            H.QuotationNo AS SoBaoGia,
            ISNULL(KH.ShortObjectName, H.ObjectID) AS KhachHang,
            H.SaleAmount AS GiaTri,
            ISNULL(C.[TINH_TRANG_BG], 'CHỜ (PENDING)') AS TrangThai,
            ISNULL(C.[LY_DO_THUA], '') AS LyDo
        FROM [OMEGA_STDD].[dbo].[OT2101] H WITH (NOLOCK)
        LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] KH WITH (NOLOCK) ON H.ObjectID = KH.ObjectID
        LEFT JOIN [dbo].[HD_CAP NHAT BAO GIA] C WITH (NOLOCK) ON H.QuotationNo = C.[MA_BAO_GIA]
        WHERE H.EmployeeID = @UserCode 
          AND H.TranYear = @TranYear AND H.TranMonth = @TranMonth
        ORDER BY H.QuotationDate DESC;
    END
END;

GO
