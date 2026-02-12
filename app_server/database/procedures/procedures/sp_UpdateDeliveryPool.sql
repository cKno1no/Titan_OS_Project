
CREATE PROCEDURE [dbo].[sp_UpdateDeliveryPool]
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @DateLimit DATE = DATEADD(day, -30, GETDATE());

    -- Bảng tạm chứa các LXH (OT2301/2302) CHƯA được giao (theo logic mới)
    SELECT 
        T_LXH_HEAD.VoucherID,
        T_LXH_HEAD.VoucherNo,
        T_LXH_HEAD.VoucherDate,
        T_LXH_HEAD.RefNo02,
        T_LXH_HEAD.ObjectID,
        T_KH.ShortObjectName AS ObjectName,
        MIN(T_LXH_DETAIL.Date01) AS EarliestRequestDate,
        SUM(T_LXH_DETAIL.ConvertedAmount) AS TotalValue,
        COUNT(T_LXH_DETAIL.TransactionID) AS ItemCount
    INTO #WaitingPool
    FROM 
        [OMEGA_STDD].[dbo].[OT2301] AS T_LXH_HEAD
    JOIN 
        [OMEGA_STDD].[dbo].[OT2302] AS T_LXH_DETAIL 
        ON T_LXH_HEAD.VoucherID = T_LXH_DETAIL.VoucherID
    LEFT JOIN 
        [OMEGA_STDD].[dbo].[IT1202] AS T_KH
        ON T_LXH_HEAD.ObjectID = T_KH.ObjectID
        
   -- *** BẮT ĐẦU LOGIC LỌC (YÊU CẦU MỚI: Chỉ loại khỏi pool khi PX (632*, 156*) đã được làm) ***
    LEFT JOIN 
        (
            -- Lấy các bản ghi WT2007 là phiếu Xuất Kho Bán Hàng (PX)
            SELECT 
                T_WH_DETAIL.OTransactionID
            FROM [OMEGA_STDD].[dbo].[WT2007] AS T_WH_DETAIL
            INNER JOIN [OMEGA_STDD].[dbo].[WT2006] AS T_WH_HEAD 
                ON T_WH_DETAIL.VoucherID = T_WH_HEAD.VoucherID
            WHERE 
                T_WH_HEAD.VoucherTypeID = 'PX'          -- Loại chứng từ là PX (Header)
                AND T_WH_DETAIL.DebitAccountID LIKE '632%'  -- Debit 632* (Giá vốn)
                AND T_WH_DETAIL.CreditAccountID LIKE '156%' -- Credit 156* (Tồn kho)
        ) AS T_Delivered
        ON T_LXH_DETAIL.ReSPTransactionID = T_Delivered.OTransactionID
    -- *** KẾT THÚC LOGIC LỌC ***

    WHERE 
        T_LXH_HEAD.VoucherDate >= @DateLimit --<<< QUET TRONG DATELIMIT - 30
        AND T_LXH_DETAIL.Date01 IS NOT NULL
        AND T_LXH_DETAIL.ActualQuantity > 0
        
        -- YÊU CẦU 1: Chỉ lấy các LXH CHƯA được giao (IS NULL)
        AND T_Delivered.OTransactionID IS NULL  -- <<< ĐÃ SỬA: Kiểm tra IS NULL trên PX
        
    GROUP BY
        T_LXH_HEAD.VoucherID, T_LXH_HEAD.VoucherNo, T_LXH_HEAD.VoucherDate, 
        T_LXH_HEAD.RefNo02, T_LXH_HEAD.ObjectID, T_KH.ShortObjectName;

    -- Bắt đầu Giao dịch Cập nhật
    BEGIN TRANSACTION;

    -- Cập nhật các LXH đã có
    UPDATE T_Plan
    SET
        T_Plan.VoucherDate = T_Pool.VoucherDate, 
        T_Plan.TotalValue = T_Pool.TotalValue,
        T_Plan.ItemCount = T_Pool.ItemCount,
        T_Plan.EarliestRequestDate = T_Pool.EarliestRequestDate,
        T_Plan.RefNo02 = T_Pool.RefNo02,
        T_Plan.LastUpdated = GETDATE()
    FROM dbo.Delivery_Weekly AS T_Plan
    JOIN #WaitingPool AS T_Pool ON T_Plan.VoucherID = T_Pool.VoucherID
    WHERE
        T_Plan.DeliveryStatus IN ('Open', 'Da Soan');

    -- Thêm các LXH mới vào Bể chờ (POOL)
    INSERT INTO dbo.Delivery_Weekly (
        VoucherID, VoucherNo, VoucherDate, RefNo02, ObjectID, ObjectName, 
        EarliestRequestDate, TotalValue, ItemCount,
        Planned_Day, DeliveryStatus, LastUpdated
    )
    SELECT
        T_Pool.VoucherID, T_Pool.VoucherNo, T_Pool.VoucherDate, T_Pool.RefNo02, T_Pool.ObjectID, T_Pool.ObjectName,
        T_Pool.EarliestRequestDate, T_Pool.TotalValue, T_Pool.ItemCount,
        'POOL', 'Open', GETDATE()
    FROM #WaitingPool AS T_Pool
    WHERE 
        NOT EXISTS (
            SELECT 1 FROM dbo.Delivery_Weekly T_Plan
            WHERE T_Plan.VoucherID = T_Pool.VoucherID
        );

      
    -- XÓA các bản ghi đã giao HƠN 90 ngày
    DELETE FROM dbo.Delivery_Weekly
    WHERE DeliveryStatus = 'Da Giao' AND ActualDeliveryDate < @DateLimit;

    COMMIT TRANSACTION;

    DROP TABLE #WaitingPool;
END
