
-- 3. SP CHI TIẾT CÔNG NỢ (AP/AR)
-- Logic: Chia bucket: Quá hạn thường (<180) và Rủi ro (>180)
CREATE PROCEDURE [dbo].[sp_GetDebt_Breakdown]
    @Type NVARCHAR(10) -- 'AR' (Phải thu) hoặc 'AP' (Phải trả)
AS
BEGIN
    IF @Type = 'AR'
    BEGIN
        SELECT 
            'Quá hạn (< 180 ngày)' as Label, 
            SUM(TotalOverdueDebt - Debt_Over_180) as Amount
        FROM [dbo].[CRM_AR_AGING_SUMMARY]
        UNION ALL
        SELECT 
            'Rủi ro (> 180 ngày)' as Label, 
            SUM(Debt_Over_180) as Amount
        FROM [dbo].[CRM_AR_AGING_SUMMARY]
    END
    ELSE
    BEGIN
        -- Với AP (Phải trả), ta giả định cấu trúc View tương tự hoặc lấy tổng quá hạn
        -- Nếu View AP chưa có cột >180, ta tạm lấy tổng quá hạn
        SELECT 
            'Nợ Quá Hạn' as Label, 
            SUM(TotalOverdueDebt) as Amount
        FROM [dbo].[CRM_AP_AGING_SUMMARY]
    END
END

GO
