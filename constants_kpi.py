# constants_kpi.py
# --- TITAN OS: SINGLE SOURCE OF TRUTH (STANDARD KPI DEFINITIONS) ---

class KPIConstants:
    """
    Hệ thống định nghĩa SQL chuẩn cho 11 chỉ số KPI cốt lõi.
    Đảm bảo hiển thị ĐÚNG 1 GIÁ TRỊ trên mọi module (Portal, CEO Cockpit, Chatbot).
    """

    # 1. DOANH SỐ (SALES REVENUE)
    # Nguồn: Sổ cái [OMEGA_STDD].[dbo].[GT9000] - Tài khoản 511
    SQL_SALES_YTD = """
        SELECT SUM(ConvertedAmount) AS TotalSales 
        FROM [OMEGA_STDD].[dbo].[GT9000] 
        WHERE CreditAccountID LIKE '511%' 
        AND TranYear = ? AND TranMonth <= ?
    """

    # 2. LỢI NHUẬN GỘP (GROSS PROFIT)
    # Nguồn: [GT9000] - Doanh số (511) trừ Giá vốn (Debit 632)
    SQL_GROSS_PROFIT_YTD = """
        SELECT 
            SUM(CASE WHEN CreditAccountID LIKE '511%' THEN ConvertedAmount ELSE 0 END) -
            SUM(CASE WHEN DebitAccountID LIKE '632%' THEN ConvertedAmount ELSE 0 END) AS GrossProfit
        FROM [OMEGA_STDD].[dbo].[GT9000]
        WHERE TranYear = ? AND TranMonth <= ?
    """

    # 3. CÔNG NỢ PHẢI THU (AR)
    # Nguồn: View tổng hợp chuẩn của Titan OS
    SQL_AR_SUMMARY = "SELECT SUM(TotalOverdueDebt + Debt_Over_180) AS TotalAR FROM CRM_AR_AGING_SUMMARY"

    # 4. CÔNG NỢ PHẢI TRẢ (AP)
    SQL_AP_SUPPLIER = "SELECT SUM(TotalDebt) AS TotalAP FROM CRM_AP_AGING_SUMMARY WHERE DebtType = 'SUPPLIER'"

    # 5. LEADTIME GIAO HÀNG (THỰC TẾ)
    # Nguồn: Chênh lệch giữa Delivery_Weekly (Thực giao) và OT2001 (Ngày duyệt đơn)
    SQL_LEADTIME_AVG = """
        SELECT AVG(DATEDIFF(day, H.OrderDate, D.ActualDeliveryDate)) AS AvgDays
        FROM [CRM_STDD].[dbo].[Delivery_Weekly] D
        INNER JOIN [OMEGA_STDD].[dbo].[OT2001] H ON D.VoucherID = H.VoucherID
        WHERE D.DeliveryStatus = 'DONE' AND H.OrderStatus IN (0, 1, 2)
    """

    # 6. ĐƠN GIÁ (UNIT PRICE)
    # Logic: So sánh giá hóa đơn (GT9000 511) với giá quy định

    # 7. GIAO HÀNG ĐÚNG HẠN (OTIF)
    SQL_OTIF_RATE = """
        SELECT (CAST(COUNT(CASE WHEN ActualDeliveryDate <= Planned_Day THEN 1 END) AS FLOAT) / 
                CAST(COUNT(*) AS FLOAT)) * 100 AS OTIF
        FROM [CRM_STDD].[dbo].[Delivery_Weekly]
        WHERE DeliveryStatus = 'DONE'
    """

    # 8. TỒN KHO KHẢ DỤNG
    # Nguồn: sp_GetInventoryAging_Cache (Tồn thực tế - Giữ chỗ cho đơn hàng)

    # 9. CÔNG NỢ QUÁ HẠN (OVERDUE DETAIL)
    # Nguồn: [OMEGA_STDD].[dbo].[AR_AgingDetail]
    SQL_AR_OVERDUE_DETAIL = """
        SELECT SUM(ConLai) AS Amount
        FROM [OMEGA_STDD].[dbo].[AR_AgingDetail]
        WHERE GETDATE() > DueDate
    """

    # 10. ĐƠN HÀNG CHỜ GIAO (SALES BACKLOG) - [ĐÃ FIX CHUẨN 100% THEO SP]
    # Nguồn: [OT2001], [OT2002] đối soát với [WT2007] và [GT9000]
    SQL_SALES_BACKLOG_SUMMARY = """
        SELECT 
            SUM(D.OrderQuantity - ISNULL(Shipped.Qty, 0)) AS BacklogQty,
            SUM(D.ConvertedAmount - (ISNULL(Shipped.Qty, 0) * D.SalePrice)) AS BacklogValue
        FROM [OMEGA_STDD].[dbo].[OT2001] H
        INNER JOIN [OMEGA_STDD].[dbo].[OT2002] D ON H.SOrderID = D.SOrderID
        OUTER APPLY (
            SELECT SUM(CASE 
                WHEN BOM.ItemQuantity > 0 THEN T1.ActualQuantity / BOM.ItemQuantity
                ELSE T1.ActualQuantity
            END) AS Qty
            FROM [OMEGA_STDD].[dbo].[WT2007] T1
            INNER JOIN [OMEGA_STDD].[dbo].[WT2006] T2 ON T1.VoucherID = T2.VoucherID
            LEFT JOIN [OMEGA_STDD].[dbo].[IT1326] BOM 
                ON BOM.InventoryID = D.InventoryID AND BOM.ItemID = T1.InventoryID
            WHERE T1.OTransactionID = D.TransactionID AND T2.VoucherTypeID = 'VC'
        ) Shipped
        LEFT JOIN [OMEGA_STDD].[dbo].[GT9000] INV ON D.TransactionID = INV.OTransactionID
        WHERE H.VoucherTypeID <> 'DTK'
          AND H.OrderStatus IN (0, 1, 2)
          AND INV.OTransactionID IS NULL
          AND H.OrderDate BETWEEN ? AND ?
    """

    # 11. NGÂN SÁCH & THỰC CHI
    # Nguồn: BUDGET_PLAN vs [GT9000] (Debit tài khoản 6% và 8%, loại trừ CP2014)
    SQL_ACTUAL_EXPENSES_BY_ANA = """
        SELECT Ana03ID, SUM(ConvertedAmount) AS Spent
        FROM [OMEGA_STDD].[dbo].[GT9000]
        WHERE (DebitAccountID LIKE '6%' OR DebitAccountID LIKE '8%')
          AND Ana03ID IS NOT NULL AND Ana03ID <> 'CP2014'
          AND TranYear = ? AND TranMonth <= ?
        GROUP BY Ana03ID
    """

    # 14. ĐỘ TRỄ XUẤT HÓA ĐƠN (WT2006 VC -> GT9000 HD)
    SQL_ACC_INVOICE_LATENCY = """
        SELECT AVG(DATEDIFF(hour, W.VoucherDate, G.VoucherDate)) as AvgHours
        FROM [OMEGA_STDD].[dbo].[WT2006] W
        INNER JOIN [OMEGA_STDD].[dbo].[WT2007] WD ON W.VoucherID = WD.VoucherID
        INNER JOIN [OMEGA_STDD].[dbo].[GT9000] G ON WD.OTransactionID = G.OTransactionID
        WHERE W.VoucherTypeID = 'VC' 
          AND G.CreditAccountID LIKE '511%'
          AND W.TranYear = ? AND W.TranMonth = ?
    """

    # 15. TỶ LỆ TREO HÓA ĐƠN (VC chưa có hóa đơn)
    SQL_ACC_PENDING_INVOICE_RATE = """
        SELECT 
            (CAST(COUNT(CASE WHEN G.OTransactionID IS NULL THEN 1 END) AS FLOAT) / 
             CAST(COUNT(*) AS FLOAT)) * 100 as PendingRate
        FROM [OMEGA_STDD].[dbo].[WT2006] W
        INNER JOIN [OMEGA_STDD].[dbo].[WT2007] WD ON W.VoucherID = WD.VoucherID
        LEFT JOIN [OMEGA_STDD].[dbo].[GT9000] G ON WD.OTransactionID = G.OTransactionID AND G.CreditAccountID LIKE '511%'
        WHERE W.VoucherTypeID = 'VC'
          AND W.TranYear = ? AND W.TranMonth = ?
    """

    # 16. SLA PHÊ DUYỆT ĐỀ NGHỊ THANH TOÁN (EXPENSE_REQUEST)
    SQL_SLA_EXPENSE_APPROVAL = """
        SELECT AVG(DATEDIFF(hour, RequestDate, ApprovalDate)) as AvgHours
        FROM [CRM_STDD].[dbo].[EXPENSE_REQUEST]
        WHERE Status = 'APPROVED' AND YEAR(RequestDate) = ? AND MONTH(RequestDate) = ?
    """

    # 17. SLA THANH TOÁN THỰC TẾ (Approval -> Payment)
    SQL_SLA_EXPENSE_PAYMENT = """
        SELECT AVG(DATEDIFF(hour, ApprovalDate, PaymentDate)) as AvgHours
        FROM [CRM_STDD].[dbo].[EXPENSE_REQUEST]
        WHERE PaymentDate IS NOT NULL AND YEAR(ApprovalDate) = ? AND MONTH(ApprovalDate) = ?
    """