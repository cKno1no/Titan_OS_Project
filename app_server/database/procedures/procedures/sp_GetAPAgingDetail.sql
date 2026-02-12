
CREATE PROCEDURE [dbo].[sp_GetAPAgingDetail]
    @VendorID NVARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Lấy danh sách Chứng từ ghi tăng nợ (Hóa đơn / Khế ước / Bảng lương)
    -- Điều kiện: Phát sinh CÓ trên các tài khoản công nợ (331, 341, 338...)
    SELECT 
        T1.VoucherID, 
        T1.VoucherNo, 
        T1.VoucherDate, 
        T1.InvoiceNo, 
        T1.ObjectID,
        T1.CreditAccountID, -- Lấy thêm AccountID để biết chi tiết tiểu khoản (VD: 341111)
        T1.VDescription AS DienGiai,
        SUM(T1.ConvertedAmount) AS OriginalAmount, -- Số tiền gốc
        
        -- Lấy hạn thanh toán từ danh mục (nếu có), mặc định 30 ngày
        ISNULL(T_KH.ReDueDays, 30) AS TermDays,
        
        -- Tính ngày đáo hạn (DueDate)
        DATEADD(DAY, ISNULL(T_KH.ReDueDays, 30), T1.VoucherDate) AS DueDate,
        
        -- Tính số ngày quá hạn (OverdueDays)
        DATEDIFF(DAY, DATEADD(DAY, ISNULL(T_KH.ReDueDays, 30), T1.VoucherDate), GETDATE()) AS OverdueDays,

        -- Phân loại hiển thị (Để tô màu trên giao diện)
        CASE 
            WHEN LEFT(T1.CreditAccountID, 3) = '341' THEN 'BANK'
            WHEN LEFT(T1.CreditAccountID, 3) = '331' THEN 'SUPPLIER'
            ELSE 'OTHER' 
        END AS DebtType

    FROM [OMEGA_STDD].[dbo].[GT9000] AS T1
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T_KH ON T1.ObjectID = T_KH.ObjectID
    WHERE 
        -- [QUAN TRỌNG]: Lọc tất cả các tài khoản đầu 3xx liên quan đến nợ phải trả
        -- Logic này sẽ bắt được 341111, 3411, 3412... bất kể độ dài
        (
           LEFT(T1.CreditAccountID, 3) IN ('331', '341', '338', '333', '334', '335')
        )
        AND T1.CreditAccountID = T1.CreditAccountID -- Đảm bảo đang xét vế Có (Tăng nợ)
        AND T1.ConvertedAmount > 0
        AND (@VendorID IS NULL OR T1.ObjectID = @VendorID)
        
    GROUP BY 
        T1.VoucherID, T1.VoucherNo, T1.VoucherDate, T1.InvoiceNo, T1.ObjectID, T1.CreditAccountID, T1.vDescription, T_KH.ReDueDays
    
    -- Sắp xếp: Ưu tiên Quá hạn lên đầu, sau đó đến ngày chứng từ cũ nhất
    ORDER BY OverdueDays DESC, VoucherDate ASC;

END
