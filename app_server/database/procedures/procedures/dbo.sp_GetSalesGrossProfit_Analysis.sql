
CREATE PROCEDURE [dbo].[sp_GetSalesGrossProfit_Analysis]
    @FromDate DATE,
    @ToDate DATE,
    @SalesmanID NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- BƯỚC 1: Lấy dữ liệu thô từ Sổ cái (GT9000)
    -- Chúng ta chỉ lấy các giao dịch có OTransactionID (những giao dịch bán hàng chuẩn)
    SELECT 
        T1.OTransactionID,
        T1.VoucherNo,
        T1.voucherDate,
        T1.ObjectID,
        T1.SalesManID,
        T1.InventoryID,
        T1.ConvertedAmount,
        T1.DebitAccountID,
        T1.CreditAccountID,
        T1.Quantity
    INTO #RawData
    FROM [OMEGA_STDD].[dbo].[GT9000] T1 WITH(NOLOCK)
    WHERE T1.voucherDate BETWEEN @FromDate AND @ToDate
      AND T1.OTransactionID IS NOT NULL 
      AND T1.OTransactionID <> '' -- Bắt buộc phải có ID liên kết
      AND (
          (T1.CreditAccountID LIKE '511%') -- Doanh thu
          OR 
          (T1.DebitAccountID LIKE '632%')  -- Giá vốn
      )
      AND (@SalesmanID IS NULL OR RTRIM(T1.SalesManID) = @SalesmanID);

    -- BƯỚC 2: Tính DOANH THU theo OTransactionID
    -- Logic: Lấy mã hàng (Kit) từ dòng ghi nhận doanh thu
    SELECT 
        OTransactionID,
        MAX(InventoryID) AS KitInventoryID, -- Lấy mã bộ (VD: MX0043)
        MAX(VoucherNo) AS VoucherNo,
        MAX(voucherDate) AS TranDate,
        MAX(ObjectID) AS ObjectID,
        MAX(SalesManID) AS SalesManID,
        SUM(ConvertedAmount) AS Revenue,
        SUM(Quantity) AS SaleQuantity
    INTO #RevenueData
    FROM #RawData
    WHERE CreditAccountID LIKE '511%'
    GROUP BY OTransactionID;

    -- BƯỚC 3: Tính GIÁ VỐN theo OTransactionID
    -- Logic: Cộng tổng giá vốn của tất cả các mã con (XC...) thuộc cùng 1 OTransactionID
    SELECT 
        OTransactionID,
        SUM(ConvertedAmount) AS COGS
    INTO #CostData
    FROM #RawData
    WHERE DebitAccountID LIKE '632%'
    GROUP BY OTransactionID;

    -- BƯỚC 4: KẾT HỢP (JOIN) VÀ LẤY THÔNG TIN CHI TIẾT
    SELECT 
        R.OTransactionID AS TransactionID_Ref,
        
        -- Thông tin Khách hàng
        R.ObjectID AS MaKhachHang,
        ISNULL(C.ShortObjectName, C.ObjectName) AS TenKhachHang,
        
        -- Thông tin Nhân viên
        ISNULL(U.SHORTNAME, R.SalesManID) AS SalesManName,
        
        -- Thông tin Chứng từ
        -- Cố gắng lấy Số đơn hàng từ bảng OT2002 thông qua OTransactionID nếu có thể
        -- Ở đây dùng VoucherNo của GT9000 (Số Hóa đơn/PXK) làm đại diện
        R.VoucherNo AS SoChungTu,
        R.VoucherNo AS SoDonHang, -- Tạm thời gán SĐH = Số CT, có thể JOIN OT2002 để lấy SOrderID chính xác
        R.TranDate AS NgayHachToan,
        
        -- Thông tin Hàng hóa (Ưu tiên mã Bộ từ dòng Doanh thu)
        R.KitInventoryID AS MaHang,
        ISNULL(I.InventoryName, R.KitInventoryID) AS TenHang,
        ISNULL(I.UnitID, '') AS DVT,
        
        -- Số liệu Tài chính
        R.SaleQuantity AS SoLuong,
        R.Revenue AS DoanhThu,
        ISNULL(K.COGS, 0) AS GiaVon,
        (R.Revenue - ISNULL(K.COGS, 0)) AS LaiGop,
        
        -- Tính % Lãi gộp (Tránh chia cho 0)
        CASE 
            WHEN R.Revenue <> 0 THEN ((R.Revenue - ISNULL(K.COGS, 0)) / R.Revenue) * 100 
            ELSE 0 
        END AS TyLeLaiGop

    FROM #RevenueData R
    -- Join Giá vốn: Left Join vì có thể có dịch vụ (GV=0)
    LEFT JOIN #CostData K ON R.OTransactionID = K.OTransactionID
    
    -- Join Danh mục
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1202] C WITH(NOLOCK) ON R.ObjectID = C.ObjectID
    LEFT JOIN [OMEGA_STDD].[dbo].[IT1302] I WITH(NOLOCK) ON R.KitInventoryID = I.InventoryID
    LEFT JOIN [CRM_STDD].[dbo].[GD - NGUOI DUNG] U WITH(NOLOCK) ON R.SalesManID = U.USERCODE

    -- Chỉ lấy dòng có Doanh thu (loại bỏ các dòng chỉ có Giá vốn mà ko tìm thấy Doanh thu tương ứng - lỗi data)
    WHERE R.Revenue <> 0 
    
    ORDER BY (R.Revenue - ISNULL(K.COGS, 0)) DESC; -- Sắp xếp theo Lãi gộp giảm dần

    -- Dọn dẹp
    DROP TABLE #RawData;
    DROP TABLE #RevenueData;
    DROP TABLE #CostData;
END

GO
