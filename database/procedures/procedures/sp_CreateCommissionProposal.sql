
CREATE PROCEDURE [dbo].[sp_CreateCommissionProposal]
    @UserCode NVARCHAR(50),
    @CustomerID NVARCHAR(20),
    @DateFrom DATE,
    @DateTo DATE,
    @CommissionRate FLOAT
AS
BEGIN
    SET NOCOUNT ON;
    -- Tắt transaction check trong SP để tránh xung đột
    SET XACT_ABORT OFF; 

    DECLARE @MaSo NVARCHAR(20) = 'BH' + FORMAT(GETDATE(), 'yyyyMMddHHmmss');

    BEGIN TRY
        -- 1. INSERT MASTER
        DECLARE @DoanhSoYTD DECIMAL(18, 0) = 0;
        SELECT @DoanhSoYTD = ISNULL(SUM(ConvertedAmount), 0)
        FROM [OMEGA_STDD].[dbo].[GT9000]
        WHERE ObjectID = @CustomerID AND TranYear = YEAR(GETDATE()) 
          AND DebitAccountID = '13111' AND CreditAccountID LIKE '5%';
          
        DECLARE @CongNo DECIMAL(18, 0) = 0;
        SELECT @CongNo = ISNULL(TotalDebt, 0)
        FROM [dbo].[CRM_AR_AGING_SUMMARY]
        WHERE ObjectID = @CustomerID;

        INSERT INTO [dbo].[DE XUAT BAO HANH_MASTER]
        (MA_SO, KHACH_HANG, TU_NGAY, DEN_NGAY, DOANH_SO_YTD, DOANH_SO_CHON, CONG_NO, MUC_CHI_PERCENT, GIA_TRI_CHI, NGUOI_LAM, TRANG_THAI, NGAY_LAM)
        VALUES 
        (@MaSo, @CustomerID, @DateFrom, @DateTo, @DoanhSoYTD, 0, @CongNo, @CommissionRate, 0, @UserCode, 'DRAFT', GETDATE());

        -- 2. INSERT DETAIL
        INSERT INTO [dbo].[DE XUAT BAO HANH_DS] (MA_SO, VOUCHERID, INVOICENO, VoucherDate, DOANH_SO, CHON)
        SELECT 
            @MaSo, Source.VoucherID, Source.InvoiceNo, Source.VoucherDate, Source.TotalAmount, 0
        FROM (
            SELECT T1.VoucherID, MAX(T1.InvoiceNo) AS InvoiceNo, MAX(T1.VoucherDate) AS VoucherDate, SUM(T1.ConvertedAmount) AS TotalAmount
            FROM [OMEGA_STDD].[dbo].[GT9000] T1
            WHERE T1.ObjectID = @CustomerID AND T1.VoucherDate BETWEEN @DateFrom AND @DateTo AND T1.DebitAccountID = '13111' AND T1.CreditAccountID LIKE '5%'
            GROUP BY T1.VoucherID
        ) AS Source
        OUTER APPLY (
            SELECT SUM(ConvertedAmount) AS DaThu FROM [OMEGA_STDD].[dbo].[GT0303] T_PAY WHERE T_PAY.DebitVoucherID = Source.VoucherID
        ) P
        WHERE (Source.TotalAmount - ISNULL(P.DaThu, 0)) <= 1000
          AND NOT EXISTS (SELECT 1 FROM [dbo].[DE XUAT BAO HANH_DS] D_EXIST WHERE D_EXIST.VOUCHERID = Source.VoucherID);

        -- 3. UPDATE MASTER
        DECLARE @TotalSelected DECIMAL(18,0);
        SELECT @TotalSelected = ISNULL(SUM(DOANH_SO), 0) FROM [dbo].[DE XUAT BAO HANH_DS] WHERE MA_SO = @MaSo AND CHON = 1;
        UPDATE [dbo].[DE XUAT BAO HANH_MASTER] SET DOANH_SO_CHON = @TotalSelected, GIA_TRI_CHI = @TotalSelected * (@CommissionRate / 100.0) WHERE MA_SO = @MaSo;

        -- 4. TRẢ VỀ KẾT QUẢ (Không Commit ở đây)
        SELECT @MaSo AS NewVoucherID;

    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR (@ErrorMessage, 16, 1);
    END CATCH
END;
