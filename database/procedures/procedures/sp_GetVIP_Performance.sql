
-- CẬP NHẬT SP KHÁCH HÀNG VIP (Dựa trên số lượng I04ID đã mua trong năm)
CREATE PROCEDURE [dbo].[sp_GetVIP_Performance]
    @Year INT
AS
BEGIN
    -- Bước 1: Tính số lượng nhóm hàng (I04ID) từng khách đã mua trong năm
    WITH CustomerI04Stats AS (
        SELECT 
            T1.ObjectID,
            COUNT(DISTINCT T2.I04ID) as PurchasedGroupCount
        FROM [OMEGA_STDD].[dbo].[GT9000] T1
        INNER JOIN [OMEGA_STDD].[dbo].[IT1302] T2 ON T1.InventoryID = T2.InventoryID
        WHERE T1.TranYear = @Year
          AND T1.CreditAccountID LIKE '511%' -- Chỉ tính trên giao dịch có doanh thu
          AND T2.I04ID IS NOT NULL AND T2.I04ID <> ''
        GROUP BY T1.ObjectID
        HAVING COUNT(DISTINCT T2.I04ID) >= 10 -- Chỉ lấy khách mua từ 10 nhóm trở lên
    ),
    
    -- Bước 2: Phân loại TITAN / DIAMOND dựa trên số lượng nhóm
    VIP_Classified AS (
        SELECT 
            ObjectID,
            CASE 
                WHEN PurchasedGroupCount > 15 THEN 'TITAN'   -- Trên 15 nhóm
                ELSE 'DIAMOND'                               -- Từ 10 đến 15 nhóm
            END as VIP_Category
        FROM CustomerI04Stats
    )

    -- Bước 3: Tính tổng Doanh số và Lợi nhuận gộp theo phân loại
    SELECT 
        V.VIP_Category as Label,
        COUNT(DISTINCT T1.ObjectID) as CustomerCount,
        
        -- Doanh thu
        SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) as Revenue,
        
        -- Lợi nhuận gộp (Doanh thu - Giá vốn)
        (SUM(CASE WHEN T1.CreditAccountID LIKE '511%' THEN T1.ConvertedAmount ELSE 0 END) -
         SUM(CASE WHEN T1.DebitAccountID LIKE '632%' THEN T1.ConvertedAmount ELSE 0 END)) as Value

    FROM [OMEGA_STDD].[dbo].[GT9000] T1
    INNER JOIN VIP_Classified V ON T1.ObjectID = V.ObjectID -- Chỉ Join với danh sách VIP đã lọc
    WHERE T1.TranYear = @Year
      AND T1.OTransactionID IS NOT NULL -- Loại bỏ các bút toán không phải bán hàng
    GROUP BY V.VIP_Category
    ORDER BY Value DESC;
END
