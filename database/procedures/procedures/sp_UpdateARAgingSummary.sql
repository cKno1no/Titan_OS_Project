
CREATE PROCEDURE dbo.sp_UpdateARAgingSummary
AS
BEGIN
    SET NOCOUNT ON;

    -- Bảng tạm Nợ (Debit) từ Sổ cái (GT9000)
    SELECT 
        T1.VoucherID, T1.ObjectID, T1.VoucherDate,
        DATEDIFF(day, T1.VoucherDate, GETDATE()) AS AgeDays,
        SUM(T1.ConvertedAmount) AS TotalInvoiceAmount
    INTO #Debits
    FROM [OMEGA_STDD].[dbo].[GT9000] AS T1
    WHERE 
        T1.DebitAccountID = '13111' 
        AND T1.CreditAccountID LIKE '5%' 
    GROUP BY 
        T1.VoucherID, T1.ObjectID, T1.VoucherDate;

    -- Bảng tạm Thanh toán (Credit) từ Bảng Giải trừ (GT0303)
    SELECT 
        T2.DebitVoucherID, T2.ObjectID,
        SUM(T2.ConvertedAmount) AS TotalPaidAmount
    INTO #Credits
    FROM [OMEGA_STDD].[dbo].[GT0303] AS T2
    WHERE 
        T2.DebitVoucherID IN (SELECT VoucherID FROM #Debits)
        AND T2.ObjectID IN (SELECT ObjectID FROM #Debits)
    GROUP BY 
        T2.DebitVoucherID, T2.ObjectID;

    -- Tính số dư của TỪNG HÓA ĐƠN
    SELECT 
        D.ObjectID, D.AgeDays,
        (D.TotalInvoiceAmount - ISNULL(C.TotalPaidAmount, 0)) AS RemainingBalance
    INTO #InvoiceBalances
    FROM #Debits AS D
    LEFT JOIN #Credits AS C 
        ON D.VoucherID = C.DebitVoucherID AND D.ObjectID = C.ObjectID
    WHERE 
        (D.TotalInvoiceAmount - ISNULL(C.TotalPaidAmount, 0)) > 1; 

    -- TỔNG HỢP (PIVOT) theo Khách hàng và 5 KHOẢNG TUỔI NỢ MỚI
    SELECT
        T_Bal.ObjectID,
        T_KH.ShortObjectName AS ObjectName,
        T_KH.SalesManID, 
        T_NV.SHORTNAME AS SalesManName,
        
        -- YÊU CẦU MỚI: Lấy hạn nợ (Giả định 1 KH chỉ có 1 hạn nợ)
        MAX(ISNULL(T_KH.ReDueDays, 0)) AS ReDueDays, 
        
        SUM(T_Bal.RemainingBalance) AS TotalDebt,
        
        -- YÊU CẦU MỚI: Tính tổng nợ QUÁ HẠN
        SUM(CASE 
            WHEN T_Bal.AgeDays > ISNULL(T_KH.ReDueDays, 0) -- Nếu Tuổi HĐ > Hạn nợ
            THEN T_Bal.RemainingBalance 
            ELSE 0 
        END) AS TotalOverdueDebt,
        
        -- (Logic 5 khoảng tuổi nợ cũ giữ nguyên)
        SUM(CASE WHEN T_Bal.AgeDays <= 0 THEN T_Bal.RemainingBalance ELSE 0 END) AS Debt_Current,
        SUM(CASE WHEN T_Bal.AgeDays BETWEEN 1 AND 30 THEN T_Bal.RemainingBalance ELSE 0 END) AS Debt_Range_1_30,
        SUM(CASE WHEN T_Bal.AgeDays BETWEEN 31 AND 90 THEN T_Bal.RemainingBalance ELSE 0 END) AS Debt_Range_31_90,
        SUM(CASE WHEN T_Bal.AgeDays BETWEEN 91 AND 180 THEN T_Bal.RemainingBalance ELSE 0 END) AS Debt_Range_91_180,
        SUM(CASE WHEN T_Bal.AgeDays > 180 THEN T_Bal.RemainingBalance ELSE 0 END) AS Debt_Over_180
        
    INTO #FinalSummary
    FROM #InvoiceBalances AS T_Bal
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] AS T_KH ON T_Bal.ObjectID = T_KH.ObjectID
    LEFT JOIN [dbo].[GD - NGUOI DUNG] AS T_NV ON T_KH.SalesManID = T_NV.USERCODE
    GROUP BY 
        T_Bal.ObjectID, T_KH.ShortObjectName, T_KH.SalesManID, T_NV.SHORTNAME;

    -- Cập nhật Bảng chính (Giao dịch an toàn)
    BEGIN TRANSACTION;
    
    TRUNCATE TABLE dbo.CRM_AR_AGING_SUMMARY;

    INSERT INTO dbo.CRM_AR_AGING_SUMMARY (
        ObjectID, ObjectName, SalesManID, SalesManName,
        ReDueDays, TotalDebt, TotalOverdueDebt, -- <-- THÊM CỘT MỚI
        Debt_Current, Debt_Range_1_30, Debt_Range_31_90, Debt_Range_91_180, Debt_Over_180,
        LastUpdated
    )
    SELECT
        ObjectID, ObjectName, SalesManID, SalesManName,
        ReDueDays, TotalDebt, TotalOverdueDebt, -- <-- THÊM DỮ LIỆU MỚI
        Debt_Current, Debt_Range_1_30, Debt_Range_31_90, Debt_Range_91_180, Debt_Over_180,
        GETDATE()
    FROM #FinalSummary;
    
    COMMIT TRANSACTION;

    -- Dọn dẹp
    DROP TABLE #Debits;
    DROP TABLE #Credits;
    DROP TABLE #InvoiceBalances;
    DROP TABLE #FinalSummary;
END
