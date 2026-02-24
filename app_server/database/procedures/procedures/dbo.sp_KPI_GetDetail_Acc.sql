
CREATE PROCEDURE [dbo].[sp_KPI_GetDetail_Acc]
    @CriteriaID VARCHAR(50),
    @UserCode VARCHAR(50),
    @TranYear INT,
    @TranMonth INT
AS
BEGIN
    SET NOCOUNT ON;

    -- ==============================================================================
    -- 1. Năng suất xử lý chứng từ (KPI_KT_01)
    -- ==============================================================================
    IF @CriteriaID = 'KPI_KT_01'
    BEGIN
        SELECT 
            VoucherNo AS SoChungTu,
            CONVERT(VARCHAR, VoucherDate, 103) AS NgayHT,
            VoucherTypeID AS LoaiPhieu,
            ISNULL(ObjectID, ObjectID) AS DoiTuong,
            OriginalAmount AS SoTien
        FROM [OMEGA_STDD].[dbo].[GT9000] WITH (NOLOCK)
        WHERE TranYear = @TranYear AND TranMonth = @TranMonth
          AND EmployeeID = @UserCode
          AND VoucherTypeID IN ('PT', 'PC', 'BN', 'BC')
        ORDER BY VoucherDate DESC, VoucherNo DESC;
    END

    -- ==============================================================================
    -- 2. Hiệu quả kiểm soát Nợ quá hạn chung (KPI_KT_02)
    -- Lấy Top 100 khách hàng nợ quá hạn cao nhất công ty để Kế toán đôn đốc
    -- ==============================================================================
    ELSE IF @CriteriaID = 'KPI_KT_02'
    BEGIN
        SELECT TOP 100
            ObjectID AS MaKH,
            ObjectName AS KhachHang,
            SalesManName AS NVKD,
            TotalDebt AS TongNo,
            TotalOverdueDebt AS NoQuaHan
        FROM [dbo].[CRM_AR_AGING_SUMMARY] WITH (NOLOCK)
        WHERE TotalOverdueDebt > 0
        ORDER BY TotalOverdueDebt DESC;
    END
END;

GO
