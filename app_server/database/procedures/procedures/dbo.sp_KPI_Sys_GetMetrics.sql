
CREATE PROCEDURE [dbo].[sp_KPI_Sys_GetMetrics]
    @TranYear INT, 
    @TranMonth INT, 
    @UserCode VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @CRM_Report_Count INT = 0;
    DECLARE @Task_Score FLOAT = 0;
    
    -- =====================================================================
    -- 1. KỶ LUẬT BÁO CÁO CRM (Đếm số lượng báo cáo tạo trên Titan OS)
    -- =====================================================================
    SELECT @CRM_Report_Count = COUNT(*)
    FROM [dbo].[HD_BAO CAO] WITH (NOLOCK)
    WHERE YEAR([NGAY]) = @TranYear AND MONTH([NGAY]) = @TranMonth 
      AND [nguoi] = @UserCode;

    -- =====================================================================
    -- 2. KỶ LUẬT THỰC THI TASK (Tách 70% Task Giao & 30% Task Tự lập)
    -- =====================================================================
    DECLARE @Assigned_Total INT = 0, @Assigned_Done INT = 0;
    DECLARE @Self_Total INT = 0;
    DECLARE @Expected_Self_Tasks INT = 22 * 7; -- 22 ngày công * 7 task/ngày = 154 tasks

    -- A. Đếm Task được cấp trên giao (Đảm bảo có CapTren hoặc SupervisorCode)
    SELECT 
        @Assigned_Total = COUNT(*),
        @Assigned_Done = SUM(CASE WHEN [Status] = 'Completed' THEN 1 ELSE 0 END)
    FROM [dbo].[Task_Master] WITH (NOLOCK)
    WHERE [UserCode] = @UserCode 
      AND YEAR([TaskDate]) = @TranYear AND MONTH([TaskDate]) = @TranMonth
      AND ([CapTren] IS NOT NULL OR [SupervisorCode] IS NOT NULL);

    -- B. Đếm Task nhân viên tự tạo kế hoạch
    SELECT @Self_Total = COUNT(*)
    FROM [dbo].[Task_Master] WITH (NOLOCK)
    WHERE [UserCode] = @UserCode 
      AND YEAR([TaskDate]) = @TranYear AND MONTH([TaskDate]) = @TranMonth
      AND [CapTren] IS NULL AND [SupervisorCode] IS NULL;

    -- C. Logic Tính Điểm 70 / 30
    DECLARE @Score_70 FLOAT = 70; -- Tự động đạt full 70 điểm nếu sếp không giao task nào
    IF @Assigned_Total > 0 
        SET @Score_70 = (@Assigned_Done * 1.0 / @Assigned_Total) * 70;

    DECLARE @Score_30 FLOAT = (@Self_Total * 1.0 / @Expected_Self_Tasks) * 30;
    IF @Score_30 > 30 
        SET @Score_30 = 30; -- Capping: Dù tạo nhiều hơn 154 task thì phần này cũng chỉ tối đa 30 điểm

    -- Tổng điểm Task
    SET @Task_Score = @Score_70 + @Score_30;

    -- ==============================================================================
    -- XUẤT KẾT QUẢ ĐỂ PYTHON BẮT LẤY
    -- ==============================================================================
    SELECT 
        ISNULL(@CRM_Report_Count, 0) AS CRM_Report_Count,
        ISNULL(@Task_Score, 0) AS Task_Completion_Rate,
        0 AS Gamification_XP; -- Tương lai sẽ dùng nếu có shop đổi điểm
END;

GO
