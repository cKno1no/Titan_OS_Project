
CREATE PROCEDURE [dbo].[sp_KPI_GetDetail_System]
    @CriteriaID VARCHAR(50), @UserCode VARCHAR(50), @TranYear INT, @TranMonth INT
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. Báo cáo CRM
    IF @CriteriaID = 'KPI_SYS_01'
    BEGIN
        SELECT 
            CONVERT(VARCHAR, [NGAY], 103) AS NgayNop,
            ISNULL([KHACH HANG], 'N/A') AS KhachHang,
            [Noi dung 1] AS NoiDung
        FROM [dbo].[HD_BAO CAO] WITH (NOLOCK)
        WHERE YEAR([NGAY]) = @TranYear AND MONTH([NGAY]) = @TranMonth 
          AND [NGUOI] = @UserCode
        ORDER BY [NGAY] DESC;
    END

    -- 2. Kỷ luật Thực thi Task
    ELSE IF @CriteriaID = 'KPI_SYS_02'
    BEGIN
        SELECT 
            CONVERT(VARCHAR, [TaskDate], 103) AS NgayTask,
            [Title] AS TenTask,
            CASE WHEN [CapTren] IS NOT NULL OR [SupervisorCode] IS NOT NULL THEN N'Được giao (70%)' ELSE N'Tự lên KH (30%)' END AS LoaiTask,
            [Status] AS TrangThai
        FROM [dbo].[Task_Master] WITH (NOLOCK)
        WHERE [UserCode] = @UserCode AND YEAR([TaskDate]) = @TranYear AND MONTH([TaskDate]) = @TranMonth
        ORDER BY [TaskDate] DESC, LoaiTask DESC;
    END
END;

GO
