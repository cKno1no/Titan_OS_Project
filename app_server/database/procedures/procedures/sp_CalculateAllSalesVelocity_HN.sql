CREATE PROCEDURE [dbo].[sp_CalculateAllSalesVelocity_HN]
AS
BEGIN
SET NOCOUNT ON;

    DECLARE @Today DATE = GETDATE();

    -- Xóa dữ liệu cũ để chuẩn bị tính toán mới
    TRUNCATE TABLE dbo.VELOCITY_SKU_CUSTOMER_HN;
    TRUNCATE TABLE dbo.VELOCITY_SKU_GROUP_HN;

    -- === BƯỚC 1: LẤY VÀ LỌC DỮ LIỆU BÁN HÀNG GỐC ===
    -- Lấy lịch sử 48 tháng của các SKU A, B, D (Req 3, 5)
    -- Và gán Nhóm hàng (Varchar05) (Req 1)
    WITH SalesHistory AS (
        SELECT 
            I.Varchar05,
            G.ObjectID,
            G.VoucherDate AS TranDate,  -- SỬA 1: Dùng VoucherDate
            G.Quantity AS Quantity      -- SỬA 2: Dùng Quantity
        FROM 
            [OMEGA_TEST].[dbo].[GT9000] AS G
        JOIN 
            [OMEGA_TEST].[dbo].[IT1302] AS I ON G.InventoryID = I.InventoryID
        WHERE 
            G.VoucherDate >= DATEADD(month, -48, @Today) -- SỬA 1
            AND G.CreditAccountID LIKE '5%' -- Đảm bảo là giao dịch bán hàng
            AND I.I01ID IN ('A', 'B', 'D') -- (Req 3) Chỉ lấy hàng dự phòng A, B, D
            AND G.Quantity > 0 -- Chỉ lấy giao dịch bán
    ),

    -- === BƯỚC 2: TÍNH TOÁN THỐNG KÊ THEO KHÁCH HÀNG (SKU-CUSTOMER) ===
    CustomerStats AS (
        SELECT 
            Varchar05,
            ObjectID,
            COUNT_BIG(DISTINCT CONVERT(date, TranDate)) AS PurchaseCount, -- Số lần mua
            DATEDIFF(month, MIN(TranDate), @Today) AS MonthsSinceFirstSale, -- Số tháng từ khi mua lần đầu
            SUM(Quantity) AS TotalQty_Last48M, -- SỬA 2
            
            -- Tính tổng SL cho 2 giai đoạn (Req 5)
            SUM(CASE WHEN TranDate >= DATEADD(month, -24, @Today) THEN Quantity ELSE 0 END) AS Qty_Last24M, -- SỬA 1, 2
            SUM(CASE WHEN TranDate < DATEADD(month, -24, @Today) THEN Quantity ELSE 0 END) AS Qty_Prev24M -- SỬA 1, 2
        FROM 
            SalesHistory
        GROUP BY 
            Varchar05, ObjectID
    )

    -- === BƯỚC 3: INSERT VÀO BẢNG CHI TIẾT (Req 4a, 4b) ===
    INSERT INTO dbo.VELOCITY_SKU_CUSTOMER_HN (
        Varchar05, 
        ObjectID, 
        Flag, 
        CustomerMonthlyVelocity, 
        TotalQty_Last48M, 
        PurchaseCount, 
        MonthsSinceFirstSale
    )
    SELECT 
        Varchar05,
        ObjectID,
        
        -- (Req 4b) Gắn cờ 'Project', 'New', 'Recurring'
        CASE 
            WHEN PurchaseCount = 1 THEN 'Project'
            WHEN MonthsSinceFirstSale <= 3 AND PurchaseCount < 2 THEN 'New'
            ELSE 'Recurring'
        END AS Flag,

        -- (Req 4a) Tính SV cho khách hàng này (dùng công thức 60/40)
        CASE 
            WHEN PurchaseCount = 1 THEN 0 -- Hàng dự án có SV = 0
            ELSE 
                -- (Req 5) Áp dụng 60% cho 24 tháng gần nhất, 40% cho 24 tháng trước đó
                ( (Qty_Last24M / 24.0) * 0.60 ) + ( (Qty_Prev24M / 24.0) * 0.40 )
        END AS CustomerMonthlyVelocity,
        
        TotalQty_Last48M,
        PurchaseCount,
        MonthsSinceFirstSale
    FROM 
        CustomerStats;

    -- === BƯỚC 4: INSERT VÀO BẢNG TỔNG (Req 5) ===
    INSERT INTO dbo.VELOCITY_SKU_GROUP_HN (
        Varchar05, 
        TotalMonthlyVelocity, 
        LeadTime_Days, 
        SafetyStock_Qty, 
        ROP
    )
    SELECT 
        V.Varchar05,
        -- (Req 5) Chỉ SUM() các khách hàng 'Recurring'
        SUM(V.CustomerMonthlyVelocity) AS TotalMonthlyVelocity,
        
        -- Lấy LeadTime/SafetyStock (Giả định lấy AVG từ các mã con)
        AVG(ISNULL(I.Amount04, 0)) AS LeadTime_Days,   -- SỬA 3: Dùng Amount04
        AVG(ISNULL(I.Amount05, 0)) AS SafetyStock_Qty, -- SỬA 4: Dùng Amount05
        
        -- (Req 2) Tính ROP = (SV * LeadTime) + SafetyStock
        -- (Velocity / 30.4) = Velocity hàng ngày
        ( (SUM(V.CustomerMonthlyVelocity) / 30.4) * AVG(ISNULL(I.Amount04, 0)) ) + AVG(ISNULL(I.Amount05, 0)) AS ROP -- SỬA 3, 4
        
    FROM 
        dbo.VELOCITY_SKU_CUSTOMER_HN AS V
    JOIN 
        [OMEGA_TEST].[dbo].[IT1302] AS I ON V.Varchar05 = I.Varchar05
    WHERE 
        V.Flag = 'Recurring' -- (Req 5) Chỉ lấy các trường hợp lặp lại
    GROUP BY 
        V.Varchar05;

    SET NOCOUNT OFF;
END;